import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Model fallback chain
# ---------------------------------------------------------------------------
# Each agent tries models in order until one succeeds.
# Override via env OPENCODE_MODELS (comma-separated, order = priority).
# ---------------------------------------------------------------------------
DEFAULT_MODELS = [
    "opencode/mimo-v2.5-free",
    "opencode/big-pickle",
    "google/gemini-2.5-pro",
    "openai/gpt-4o",
]


def _get_model_chain() -> list[str]:
    """Return model list from env or default."""
    raw = os.environ.get("OPENCODE_MODELS")
    if raw and raw.strip():
        return [m.strip() for m in raw.split(",") if m.strip()]
    return DEFAULT_MODELS


def run_agent(
    role: str,
    prompt_template_path: str,
    format_kwargs: dict,
    work_dir: str,
    expected_output_file: str,
    timeout: int = 1200,
    models: list[str] | None = None,
) -> str:
    """
    Запускает OpenCode с промптом из файла.
    Пробует модели из списка по очереди — первая успешная побеждает.

    Args:
        role: Имя агента (market, sentiment, …)
        prompt_template_path: Путь к .md шаблону промпта
        format_kwargs: Данные для подстановки в промпт
        work_dir: Рабочая директория запуска (run_dir)
        expected_output_file: Путь к ожидаемому выходному файлу
        timeout: Таймаут на один запуск opencode (сек)
        models: Список моделей в порядке приоритета. None = DEFAULT_MODELS

    Returns:
        stdout от opencode (при успехе)

    Raises:
        RuntimeError: если ВСЕ модели упали
    """
    with open(prompt_template_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # Fill in the placeholders
    prompt = prompt_template
    for k, v in format_kwargs.items():
        prompt = prompt.replace(f"{{{k}}}", str(v))

    model_chain = models if models is not None else _get_model_chain()

    prompt_file = os.path.join(work_dir, f"{role}_prompt.md")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    last_error = ""

    for idx, model in enumerate(model_chain):
        logger.info(f"Running agent: {role}  |  model [{idx+1}/{len(model_chain)}]: {model}")

        cmd = [
            "opencode", "run",
            "-m", model,
            f"Read instructions from {prompt_file} and execute them. "
            f"Ensure you write the final report exactly to the specified file path.",
            "--auto",
        ]

        logger.info(f"  Executing: {' '.join(cmd[:4])} ...")

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ},
            )
        except subprocess.TimeoutExpired:
            last_error = f"Timeout ({timeout}s)"
            logger.warning(f"  Model {model} timed out for {role}, trying next…")
            continue
        except Exception as e:
            last_error = str(e)
            logger.warning(f"  Model {model} error for {role}: {e}, trying next…")
            continue

        if result.returncode != 0:
            last_error = result.stderr.strip() or f"exit code {result.returncode}"
            is_rate = any(
                kw in (result.stderr + result.stdout).lower()
                for kw in ("rate limit", "429", "too many", "quota", "limit reached")
            )
            if is_rate:
                logger.warning(f"  Model {model} rate-limited for {role}, trying next…")
            else:
                logger.warning(
                    f"  Model {model} failed for {role} "
                    f"(exit {result.returncode}), trying next…\n"
                    f"  stderr: {result.stderr[:300]}"
                )
            continue

        # Success
        expected_path = os.path.join(work_dir, expected_output_file)
        if not os.path.exists(expected_path):
            logger.warning(
                f"  Model {model} OK but output file not found: {expected_output_file}"
            )
        else:
            logger.info(f"  Model {model} — success ({expected_output_file})")

        return result.stdout

    # All models failed
    msg = (
        f"All {len(model_chain)} models failed for agent '{role}'.\n"
        f"Last error: {last_error[:500]}"
    )
    logger.error(msg)
    raise RuntimeError(msg)
