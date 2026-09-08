<script lang="ts">
    import Form from "$lib/ui/Components/Form";
    import { FormGroup } from "$lib/ui/Components/Form";
    import * as Input from "$lib/ui/Components/Input";
    import * as Button from "$lib/ui/Components/Button";
    import Label from "$lib/ui/Components/Label";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { showThis as showContent } from "$lib/ui/Layout/Landing/Register.svelte";
    import MnemonicDisplay from "./MnemonicDisplay.svelte";
    import { naradaIdentity } from "$lib/narada/identity.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";

    let isGenerating = $state(false);

    const handleGenerate = async (e: Event) => {
        const form = e.target as HTMLFormElement;
        const formData = new FormData(form);
        const accountId = formData.get("account_id") as string;

        if (!accountId || accountId.trim().length === 0) {
            showMessage({ title: "Please enter an account ID." });
            return;
        }

        isGenerating = true;
        try {
            const result = await naradaIdentity.generateIdentity(accountId.trim());
            if (result) {
                showContent(MnemonicDisplay, {
                    publicId: result.publicId,
                    mnemonicToken: result.mnemonicToken,
                    accountId: accountId.trim(),
                });
            } else {
                showMessage({
                    title: "Failed to generate identity. It may already exist.",
                });
            }
        } catch (err) {
            showMessage({
                title: "Connection error. Is the server running?",
            });
        } finally {
            isGenerating = false;
        }
    };

    const handleRecover = () => {
        import("./RecoverIdentity.svelte").then((mod) => {
            showContent(mod.default);
        });
    };
</script>

<Form onsubmit={handleGenerate}>
    <FormGroup>
        <Label for="account_id">Account ID</Label>
        <Input.Basic
            type="text"
            name="account_id"
            id="account_id"
            placeholder="e.g. alice@example.com"
            value={SharedStore.accounts.length > 0 ? SharedStore.accounts[0].email_address : ""}
            autocomplete="off"
            autofocus
            required
        />
        <span class="muted">
            Your Narada identity will be tied to this account.
        </span>
    </FormGroup>
    <div class="landing-body-footer">
        <Button.Basic type="submit" class="btn-cta" disabled={isGenerating}>
            {isGenerating ? "Generating..." : "Generate Identity"}
        </Button.Basic>
        <Button.Basic type="button" class="btn-inline" onclick={handleRecover}>
            Recover from mnemonic
        </Button.Basic>
    </div>
</Form>

<style>
    .muted {
        font-size: var(--font-size-xs);
        color: var(--color-text-secondary);
    }
</style>
