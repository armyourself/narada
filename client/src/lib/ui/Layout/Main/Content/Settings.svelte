<script lang="ts">
    import Menu from "./Settings/Menu.svelte";
    import Content, { backToDefault as showDefaultSettings } from "./Settings/Content.svelte";
    import General from "./Settings/Content/General.svelte";
    import Form from "$lib/ui/Components/Form";
    import { onMount } from "svelte";
    import { PreferenceManager } from "$lib/preferences";

    const saveChanges = async (): Promise<void> => {
        await PreferenceManager.savePreferences();
    };

    onMount(() => {
        showDefaultSettings();
    })
</script>

<div class="settings">
    <Form onsubmit={saveChanges} style="height:100%;">
        <Menu />
        <Content>
            <General />
        </Content>
    </Form>
</div>

<style>
    :global {
        .settings {
            position: absolute;
            top: 88px;
            left: 268px;
            bottom: 22px;
            right: 22px;
            z-index: 2;
            background: var(--glass);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
    }
</style>
