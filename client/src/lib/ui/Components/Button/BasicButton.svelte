<script lang="ts">
    import { type Snippet } from "svelte";
    import { combine } from "$lib/utils";

    interface Props {
        children: Snippet;
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

<button
    class={combine("btn", additionalClass)}
    {...restAttributes}
>
    {@render children()}
</button>

<style>
    :global {
        .btn {
            padding: var(--spacing-xs) var(--spacing-sm);
            border: none;
            border-radius: 100px;
            cursor: pointer;
            transition: all var(--transition-fast) var(--ease-default);
            font-size: var(--font-size-sm);
            font-family: var(--ui);
            font-weight: 500;
            display: flex;
            align-items: center;
            justify-content: center;

            &:hover,
            &.hover {
                transform: translateY(-1px);
            }

            &:active,
            &.active {
                transform: translateY(0);
            }

            &.btn-cta {
                width: 100%;
                font-weight: 600;
                background: var(--accent);
                color: #fff;
                padding: 10px 20px;
                box-shadow: 0 4px 14px rgba(203, 154, 115, 0.20);

                &:hover {
                    background: #BA855D;
                    box-shadow: 0 8px 20px rgba(203, 154, 115, 0.28);
                }
            }

            &.btn-inline {
                padding: var(--spacing-2xs) var(--spacing-sm);
                margin: 0;
                background-color: transparent;
                color: var(--ink-dim);
                border-radius: 100px;

                &:hover,
                &.hover {
                    background: var(--glass-strong);
                    color: var(--ink);
                }
            }

            &.btn-outline {
                background: var(--glass-strong);
                color: var(--ink-dim);
                border: 1px solid var(--glass-border);
                padding: 8px 14px;
                border-radius: 100px;

                &:hover,
                &.hover {
                    background: #fff;
                    color: var(--ink);
                }
            }

            &:has(svg) {
                justify-content: space-between;

                & svg {
                    margin-right: var(--spacing-xs);
                    margin-left: calc(-0.5 * var(--spacing-xs));
                }

                &:not(:has(span)) svg {
                    margin-right: calc(-0.5 * var(--spacing-xs));
                }
            }

            &.btn-md {
                font-size: var(--font-size-xs);
            }

            &.btn-sm {
                padding: var(--spacing-2xs) var(--spacing-sm)!important;
                font-size: var(--font-size-xs);

                & svg {
                    width: var(--font-size-md);
                    height: var(--font-size-md);
                }
            }
        }
    }
</style>
