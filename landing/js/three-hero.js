/**
 * Three.js Scroll-Only 3D Scene
 * Camera dolly zoom controlled by scroll progress.
 * Candlestick chart constantly refreshes (live market feel).
 */

(function () {
    if (typeof THREE === 'undefined') return;

    const container = document.getElementById('heroCanvas');
    if (!container) return;

    // ── Scene ──
    const scene = new THREE.Scene();

    // ── Camera ──
    const camera = new THREE.PerspectiveCamera(
        45, container.clientWidth / container.clientHeight, 0.1, 100
    );
    camera.position.set(0, 2, 20);
    camera.lookAt(0, 0, 0);

    // ── Renderer ──
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // ── Lights ──
    scene.add(new THREE.AmbientLight(0x222244, 0.5));
    const dir = new THREE.DirectionalLight(0xffffff, 0.7);
    dir.position.set(5, 10, 7);
    scene.add(dir);
    const greenLight = new THREE.DirectionalLight(0x22c55e, 0.3);
    greenLight.position.set(-8, 3, 5);
    scene.add(greenLight);

    // ── Grid floor ──
    const grid = new THREE.GridHelper(28, 16, 0x1a2a1a, 0x0f1a0f);
    grid.position.y = -3;
    scene.add(grid);

    // ── Materials ──
    const upMat = new THREE.MeshPhysicalMaterial({
        color: 0x22c55e, emissive: 0x22c55e, emissiveIntensity: 0.15,
        metalness: 0.3, roughness: 0.4,
    });
    const downMat = new THREE.MeshPhysicalMaterial({
        color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 0.1,
        metalness: 0.3, roughness: 0.4,
    });
    const wickMat = new THREE.MeshPhysicalMaterial({
        color: 0x8899aa, metalness: 0.2, roughness: 0.5,
    });
    const glowMat = new THREE.MeshBasicMaterial({
        color: 0x22c55e, transparent: true, opacity: 0.06,
    });

    // ── Candle data ──
    const CANDLE_COUNT = 35;
    const BW = 0.45, BD = 0.4;
    let price = 100;
    const candles = [];

    // Generate initial candles
    for (let i = 0; i < CANDLE_COUNT; i++) {
        const open = price;
        const change = (Math.random() - 0.47) * 5;
        const close = open + change;
        const high = Math.max(open, close) + Math.random() * 1.5;
        const low = Math.min(open, close) - Math.random() * 1.5;
        candles.push({
            open, close, high, low,
            isUp: close >= open,
            x: i - CANDLE_COUNT / 2,
        });
        price = close;
    }

    // Meshes
    const group = new THREE.Group();
    scene.add(group);
    const bodies = [];
    const wicks = [];
    const glows = [];

    function buildCandle(c, index) {
        const bh = Math.abs(c.close - c.open) || 0.1;
        const by = (c.close + c.open) / 2 - 100;
        const mat = c.isUp ? upMat : downMat;

        // Body
        const body = new THREE.Mesh(new THREE.BoxGeometry(BW, bh, BD), mat);
        body.position.set(c.x, by, 0);
        group.add(body);
        bodies.push(body);

        // Glow
        const glow = new THREE.Mesh(
            new THREE.BoxGeometry(BW + 0.08, bh + 0.08, BD + 0.08),
            glowMat,
        );
        glow.position.copy(body.position);
        group.add(glow);
        glows.push(glow);

        // Wick
        const wh = c.high - c.low;
        if (wh > bh) {
            const wick = new THREE.Mesh(
                new THREE.CylinderGeometry(0.035, 0.035, wh, 4),
                wickMat,
            );
            wick.position.set(c.x, (c.high + c.low) / 2 - 100, 0);
            group.add(wick);
            wicks.push(wick);
        }
    }

    // Build all initial candles
    for (let i = 0; i < candles.length; i++) {
        buildCandle(candles[i], i);
    }

    // ── Scroll progress ──
    let scrollProgress = 0;
    let lastScrollUpdate = 0;
    window.addEventListener('scroll', () => {
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        scrollProgress = docHeight > 0 ? scrollTop / docHeight : 0;
    }, { passive: true });

    // ── Resize ──
    function onResize() {
        const w = container.clientWidth;
        const h = container.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
    }
    window.addEventListener('resize', onResize);

    // ── Smoothstep ──
    function lerp(a, b, t) { return a + (b - a) * Math.max(0, Math.min(1, t)); }

    // ── Shift candles: drop oldest, push new at end ──
    let frameCounter = 0;

    function shiftCandles() {
        frameCounter++;

        // Every 6 frames, shift: drop first candle, add new at end
        if (frameCounter % 6 !== 0) return;

        // Remove first candle's meshes
        const removed = candles.shift();
        const removedIdx = candles.length; // old length after shift

        // Remove meshes for the shifted-out candle (the one at removedIdx)
        // Actually, we remove all meshes and rebuild to keep it simple
        // Since we have 35 candles and shift every 6 frames, this rebuild
        // is fine performance-wise.

        // Remove all old meshes
        bodies.forEach(m => { group.remove(m); m.geometry.dispose(); });
        wicks.forEach(m => { group.remove(m); m.geometry.dispose(); });
        glows.forEach(m => { group.remove(m); m.geometry.dispose(); });
        bodies.length = 0;
        wicks.length = 0;
        glows.length = 0;

        // Generate new candle at end
        const last = candles[candles.length - 1];
        const newOpen = last.close;
        const newChange = (Math.random() - 0.47) * 5;
        const newClose = newOpen + newChange;
        candles.push({
            open: newOpen,
            close: newClose,
            high: Math.max(newOpen, newClose) + Math.random() * 1.5,
            low: Math.min(newOpen, newClose) - Math.random() * 1.5,
            isUp: newClose >= newOpen,
            x: candles.length - CANDLE_COUNT / 2,
        });

        // Shift all x positions
        for (let i = 0; i < candles.length; i++) {
            candles[i].x = i - CANDLE_COUNT / 2;
        }

        // Rebuild all meshes
        for (let i = 0; i < candles.length; i++) {
            const c = candles[i];
            const bh = Math.abs(c.close - c.open) || 0.1;
            const by = (c.close + c.open) / 2 - 100;
            const mat = c.isUp ? upMat : downMat;

            const body = new THREE.Mesh(new THREE.BoxGeometry(BW, bh, BD), mat);
            body.position.set(c.x, by, 0);
            group.add(body);
            bodies.push(body);

            const glowGeo = new THREE.BoxGeometry(BW + 0.08, bh + 0.08, BD + 0.08);
            const glowM = new THREE.MeshBasicMaterial({
                color: c.isUp ? 0x22c55e : 0xef4444,
                transparent: true, opacity: 0.05,
            });
            const glow = new THREE.Mesh(glowGeo, glowM);
            glow.position.copy(body.position);
            group.add(glow);
            glows.push(glow);

            const wh = c.high - c.low;
            if (wh > bh) {
                const wick = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.035, 0.035, wh, 4),
                    wickMat,
                );
                wick.position.set(c.x, (c.high + c.low) / 2 - 100, 0);
                group.add(wick);
                wicks.push(wick);
            }
        }
    }

    // ── Animation loop ──
    function animate() {
        requestAnimationFrame(animate);

        const s = scrollProgress;

        // ── Camera: ONLY scroll-controlled dolly zoom ──
        // Scroll 0 → camera far (zoom out), scroll 1 → camera close (zoom in)
        const zMin = 2.5;  // closest
        const zMax = 20;    // farthest
        const camZ = lerp(zMax, zMin, s);
        camera.position.z = camZ;

        // Slight upward tilt as you zoom in
        const camY = lerp(2, 0.5, s);
        camera.position.y = camY;
        camera.lookAt(0, lerp(0, -0.3, s), 0);

        // ── Candles constantly shift (refresh) ──
        shiftCandles();

        renderer.render(scene, camera);
    }

    animate();
})();
