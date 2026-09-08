<script lang="ts">
    import { combine } from "$lib/utils";

    interface Props {
        group?: string[] | undefined;
        value?: string;
        element?: HTMLInputElement;
        [attribute: string]: unknown;
    }

    let {
        group = $bindable(undefined),
        value = $bindable(undefined),
        element = $bindable(undefined),
        ...attributes
    }: Props  = $props();

    let {
	    class: additionalClass,
		...restAttributes
	} = $derived(attributes);

    const handleChange = ({ target }: any) => {
        if (!group) return;
		const { value, checked } = target;
		if (checked) group.push(value);
		else group = group.filter(v => v !== value);
	}
</script>

{#if restAttributes["type"] === "checkbox"}
    <input
        type="checkbox"
        bind:this={element}
        {value}
        checked={group?.includes(value as string)}
        onchange={handleChange}
        class={combine("input", additionalClass)}
        {...restAttributes}
    />
{:else}
    <input
        bind:this={element}
        bind:value
        class={combine("input", additionalClass)}
        {...restAttributes}
    />
{/if}

<style>
    :global{
        .input {
            width: 100%;
            padding: 9px 14px;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-sm);
            color: var(--ink);
            font-size: var(--font-size-sm);
            transition: all var(--transition-fast) var(--ease-default);
        }

        .input::placeholder { color: var(--ink-faint); }

        .input:focus {
            outline: none;
            border-color: var(--accent);
            background: var(--glass);
        }

        .input[type="email"] {
            will-change: transform;
        }

        .input[type="checkbox"] {
            padding: 0;
            appearance: none;
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 6px;
            background: var(--glass-strong);
            border: 1px solid var(--glass-border);
            cursor: pointer;
            position: relative;
        }

        .input[type="checkbox"]:checked {
            background: var(--accent);
            border-color: var(--accent);
        }

        .input[type="checkbox"]:checked::after {
            content: "";
            position: absolute;
            top: 2px;
            left: 5px;
            width: 4px;
            height: 8px;
            border: solid #fff;
            border-width: 0 2px 2px 0;
            transform: rotate(45deg);
        }

        .input + .muted {
            margin-left: calc(var(--spacing-2xs) / 2);
            margin-top: var(--spacing-xs);
        }
    }
</style>
