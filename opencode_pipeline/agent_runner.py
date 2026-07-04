import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_agent(role: str, prompt_template_path: str, format_kwargs: dict, work_dir: str, expected_output_file: str, timeout: int = 1200) -> str:
    """
    Запускает OpenCode с промптом из файла.
    OpenCode работает в work_dir и может создавать/читать файлы там.
    """
    with open(prompt_template_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # Fill in the placeholders
    # Because some data could have curly braces, we might need a custom safe formatter or just simple replace
    prompt = prompt_template
    for k, v in format_kwargs.items():
        prompt = prompt.replace(f"{{{k}}}", str(v))

    logger.info(f"Running agent: {role}")
    
    # We will write the prompt to a temp file and tell opencode to read it if it's too long
    # But since it's via subprocess, we can just pass it directly if we want
    # Better to write prompt to a temp file in work_dir
    prompt_file = os.path.join(work_dir, f"{role}_prompt.md")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    # We use non-interactive mode as tested
    # "read {prompt_file} and perform the task"
    cmd = ["opencode", "run", "-m", "opencode/mimo-v2.5-free",
           f"Read instructions from {prompt_file} and execute them. Ensure you write the final report exactly to the specified file path.",
           "--auto"]

    logger.info(f"Executing: {' '.join(cmd)}")
    
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ}
    )

    if result.returncode != 0:
        logger.error(f"OpenCode failed: {result.stderr}")
        raise RuntimeError(f"OpenCode failed for {role}: {result.stderr}")

    expected_path = os.path.join(work_dir, expected_output_file)
    if not os.path.exists(expected_path):
        logger.warning(f"Expected output file {expected_output_file} was not found at {expected_path} after agent run.")
    else:
        logger.info(f"Output generated successfully at {expected_output_file}")
        
    return result.stdout
