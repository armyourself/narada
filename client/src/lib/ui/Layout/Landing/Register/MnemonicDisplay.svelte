<script lang="ts">
    import { onMount } from "svelte";
    import * as Button from "$lib/ui/Components/Button";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { NaradaIdentityService } from "$lib/services/NaradaIdentityService";
    import { showThis as showContent } from "$lib/ui/Layout/Landing/Register.svelte";
    import Accounts from "./Accounts.svelte";

    let { publicId, mnemonicToken, accountId } = $props();

    let mnemonic = $state<string | null>(null);
    let mnemonicCopied = $state(false);
    let loading = $state(true);
    let error = $state<string | null>(null);

    onMount(async () => {
        try {
            const result = await NaradaIdentityService.claimMnemonic(accountId, mnemonicToken);
            if (result && result.mnemonic) {
                mnemonic = result.mnemonic;
            } else {
                error = "Mnemonic could not be retrieved. The token may have expired.";
            }
        } catch {
            error = "Failed to fetch mnemonic from server.";
        } finally {
            loading = false;
        }
    });

    const copyMnemonic = async () => {
        if (mnemonic) {
            await navigator.clipboard.writeText(mnemonic);
            mnemonicCopied = true;
            setTimeout(() => (mnemonicCopied = false), 2000);
        }
    };

    const handleContinue = () => {
        showContent(Accounts);
    };
</script>

<div class="mnemonic-container">
    <div class="mnemonic-header">
        <h3>Your Narada Identity</h3>
        <p class="public-id-label">Public ID</p>
        <code class="public-id">{publicId}</code>
    </div>

    <div class="mnemonic-section">
        <h4>Recovery Mnemonic</h4>
        {#if loading}
            <p class="muted">Loading mnemonic...</p>
        {:else if error}
            <p class="error">{error}</p>
        {:else if mnemonic}
            <div class="mnemonic-box">
                <code class="mnemonic-text">{mnemonic}</code>
            </div>
            <Button.Basic type="button" class="btn-outline" onclick={copyMnemonic}>
                {mnemonicCopied ? "Copied!" : "Copy to clipboard"}
            </Button.Basic>
        {/if}
    </div>

    <div class="mnemonic-warning">
        <strong>Write this down!</strong> This is the only way to recover your
        identity. If you lose it, your identity cannot be restored.
    </div>

    <div class="landing-body-footer">
        <Button.Basic type="button" class="btn-cta" onclick={handleContinue}>
            I have saved my mnemonic
        </Button.Basic>
    </div>
</div>

<style>
    .mnemonic-container {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-lg);
    }

    .mnemonic-header {
        text-align: center;
    }

    .mnemonic-header h3 {
        margin-bottom: var(--spacing-sm);
    }

    .public-id-label {
        font-size: var(--font-size-xs);
        color: var(--color-text-secondary);
        margin-bottom: var(--spacing-2xs);
    }

    .public-id {
        display: block;
        padding: var(--spacing-xs);
        background: var(--color-bg-secondary);
        border-radius: var(--radius-sm);
        font-size: var(--font-size-xs);
        word-break: break-all;
        font-family: monospace;
    }

    .mnemonic-section {
        text-align: center;
    }

    .mnemonic-section h4 {
        margin-bottom: var(--spacing-sm);
    }

    .mnemonic-box {
        padding: var(--spacing-sm);
        background: var(--color-bg-secondary);
        border: 1px dashed var(--color-border);
        border-radius: var(--radius-sm);
        margin-bottom: var(--spacing-sm);
    }

    .mnemonic-text {
        font-family: monospace;
        font-size: var(--font-size-sm);
        word-break: break-word;
        user-select: all;
    }

    .mnemonic-warning {
        padding: var(--spacing-sm);
        background: var(--color-bg-secondary);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-sm);
        font-size: var(--font-size-xs);
        text-align: center;
    }

    .muted {
        font-size: var(--font-size-xs);
        color: var(--color-text-secondary);
    }

    .error {
        color: var(--color-error, #e74c3c);
        font-size: var(--font-size-xs);
    }
</style>
