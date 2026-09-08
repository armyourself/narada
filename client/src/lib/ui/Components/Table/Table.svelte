<script lang="ts">
    import { type Snippet } from "svelte";
    import { combine } from "$lib/utils";

    interface Props {
        children: Snippet
        [attribute: string]: unknown;
    }

    let {
        children,
        ...attributes
    }: Props  = $props();

	let {
	    class: additionalClass,
		...restAttributes
	} = $derived(attributes);
</script>

<table
    class={combine("table", additionalClass)}
    {...restAttributes}
>
    {@render children()}
</table>

<style>
    :global {
        .table {
            width: 100%;
            border-spacing: 0;
            border-radius: var(--radius-sm);
            border-collapse: separate;
            border-spacing: 0;
        }

        .table .tr {
            transition: background 0.15s ease;
        }

        .table .tr:hover {
            background: var(--glass-strong);
        }

        .table .th {
            font-family: var(--ui);
            font-size: var(--font-size-xs);
            font-weight: 600;
            color: var(--ink-faint);
            text-align: left;
            padding: var(--spacing-sm) var(--spacing-md);
            border-bottom: 1px solid var(--glass-border);
        }

        .table .td {
            padding: var(--spacing-sm) var(--spacing-md);
            border-bottom: 1px solid var(--glass-border);
            font-size: var(--font-size-sm);
        }
    }
</style>
