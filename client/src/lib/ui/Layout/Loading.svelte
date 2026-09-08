<script lang="ts">
    import { Spinner } from "$lib/ui/Components/Loader";
</script>

<div class="loading-page">
    <div class="loading-card">
        <Spinner size="medium"/>
        <h3>Connecting to accounts...</h3>
    </div>
</div>

<style>
    .loading-page {
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: row;
        justify-content: center;
        align-items: center;
    }

    .loading-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--spacing-md);
        background: var(--glass);
        backdrop-filter: blur(18px) saturate(1.4);
        -webkit-backdrop-filter: blur(18px) saturate(1.4);
        border: 1px solid var(--glass-border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: var(--spacing-xl) var(--spacing-2xl);
    }

    .loading-card h3 {
        font-family: var(--ui);
        font-size: var(--font-size-sm);
        color: var(--ink-dim);
    }
</style>
