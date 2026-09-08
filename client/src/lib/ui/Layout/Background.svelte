<div class="bg">
    <div class="blob b1"></div>
    <div class="blob b2"></div>
    <div class="blob b3"></div>
    <div class="blob b4"></div>
</div>

<style>
    .bg {
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        background: linear-gradient(160deg, var(--cream) 0%, var(--hue-1) 32%, var(--hue-2) 58%, var(--hue-3) 80%, var(--hue-4) 100%);
        pointer-events: none;
    }
    .blob {
        position: absolute;
        border-radius: 50%;
        filter: blur(90px);
        opacity: 0.4;
        will-change: transform;
    }
    .blob.b1 { width: 560px; height: 560px; background: var(--hue-1); top: -220px; left: -160px; animation: driftA 34s ease-in-out infinite; }
    .blob.b2 { width: 480px; height: 480px; background: var(--hue-2); bottom: -220px; right: -140px; animation: driftB 40s ease-in-out infinite; }
    .blob.b3 { width: 380px; height: 380px; background: var(--hue-3); top: 32%; left: 42%; animation: driftC 30s ease-in-out infinite; }
    .blob.b4 { width: 420px; height: 420px; background: var(--hue-4); top: 8%; right: 12%; animation: driftD 36s ease-in-out infinite; }

    @keyframes driftA {
        0% { transform: translate(0, 0) scale(1); }
        25% { transform: translate(90px, 60px) scale(1.1); }
        50% { transform: translate(40px, 140px) scale(0.95); }
        75% { transform: translate(-60px, 50px) scale(1.05); }
        100% { transform: translate(0, 0) scale(1); }
    }
    @keyframes driftB {
        0% { transform: translate(0, 0) scale(1); }
        30% { transform: translate(-80px, -70px) scale(1.08); }
        60% { transform: translate(-30px, -140px) scale(0.96); }
        100% { transform: translate(0, 0) scale(1); }
    }
    @keyframes driftC {
        0% { transform: translate(0, 0) scale(1); }
        33% { transform: translate(70px, -50px) scale(1.12); }
        66% { transform: translate(-70px, 40px) scale(0.9); }
        100% { transform: translate(0, 0) scale(1); }
    }
    @keyframes driftD {
        0% { transform: translate(0, 0) scale(1); }
        40% { transform: translate(-60px, 80px) scale(1.06); }
        70% { transform: translate(50px, 40px) scale(0.94); }
        100% { transform: translate(0, 0) scale(1); }
    }

    @media (prefers-reduced-motion: reduce) {
        .blob { animation: none; }
    }
</style>
