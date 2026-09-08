<script lang="ts">
    import Form from "$lib/ui/Components/Form";
    import { FormGroup } from "$lib/ui/Components/Form";
    import * as Input from "$lib/ui/Components/Input";
    import * as Button from "$lib/ui/Components/Button";
    import Label from "$lib/ui/Components/Label";
    import { show as showMessage } from "$lib/ui/Components/Message";
    import { showThis as showContent } from "$lib/ui/Layout/Landing/Register.svelte";
    import Accounts from "./Accounts.svelte";
    import { naradaIdentity } from "$lib/narada/identity.svelte";
    import { SharedStore } from "$lib/stores/shared.svelte";
    import GenerateIdentity from "./GenerateIdentity.svelte";

    let isRecovering = $state(false);

    const handleRecover = async (e: Event) => {
        const form = e.target as HTMLFormElement;
        const formData = new FormData(form);
        const accountId = formData.get("account_id") as string;
        const mnemonic = formData.get("mnemonic") as string;

        if (!accountId || accountId.trim().length === 0) {
            showMessage({ title: "Please enter an account ID." });
            return;
        }

        if (!mnemonic || mnemonic.trim().length === 0) {
            showMessage({ title: "Please enter your recovery mnemonic." });
            return;
        }

        isRecovering = true;
        try {
            const publicId = await naradaIdentity.recoverIdentity(
                accountId.trim(),
                mnemonic.trim()
            );
            if (publicId) {
                showMessage({
                    title: "Identity recovered!",
                    details: `Your public ID: <code>${publicId}</code>`,
                });
                showContent(Accounts);
            } else {
                showMessage({
                    title: "Recovery failed. Check your mnemonic and try again.",
                });
            }
        } catch (err) {
            showMessage({
                title: "Connection error. Is the server running?",
            });
        } finally {
            isRecovering = false;
        }
    };

    const handleBack = () => {
        showContent(GenerateIdentity);
    };
</script>

<Form onsubmit={handleRecover}>
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
    </FormGroup>
    <FormGroup>
        <Label for="mnemonic">Recovery Mnemonic</Label>
        <Input.Basic
            type="text"
            name="mnemonic"
            id="mnemonic"
            placeholder="Enter your 12-word recovery phrase"
            autocomplete="off"
            required
        />
        <span class="muted">
            Enter the mnemonic you saved when generating your identity.
        </span>
    </FormGroup>
    <div class="landing-body-footer">
        <Button.Basic type="submit" class="btn-cta" disabled={isRecovering}>
            {isRecovering ? "Recovering..." : "Recover Identity"}
        </Button.Basic>
        <Button.Basic type="button" class="btn-inline" onclick={handleBack}>
            Back to generate
        </Button.Basic>
    </div>
</Form>

<style>
    .muted {
        font-size: var(--font-size-xs);
        color: var(--color-text-secondary);
    }
</style>
