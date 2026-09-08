<script lang="ts">
    import { onDestroy } from "svelte";
    import { close, type Props } from "./index";
    import * as Button from "$lib/ui/Components/Button";
    import Icon from "$lib/ui/Components/Icon";
    import Collapse from "$lib/ui/Components/Collapse";
    import { combine } from "$lib/utils";
    import { DEFAULT_LANGUAGE } from "$lib/constants";
    import { local } from "$lib/locales";

    interface PropsWithMountId extends Props {
        id: string;
    }

    let {
        id,
        content,
        type,
        closeable,
        details,
        onManage,
        onManageText,
        ...attributes
    }: PropsWithMountId = $props();

    let {
	    class: additionalClass,
		...restAttributes
	} = $derived(attributes);

    let alert: HTMLElement;
    onDestroy(() => {
        dismiss();
    });

    function dismiss() {
        alert.classList.remove("show");
        close(id);
    }

    const onManageWrapper = async (e: Event) => {
        if (onManage) onManage(e);
        dismiss();
    }
</script>

<div
    bind:this={alert}
    class={combine("alert show", type, additionalClass)}
    {...restAttributes}
>
    <div class="alert-body">
        <div class="alert-body-text">
            <div class="alert-icon">
                <Icon name={type} />
            </div>
            <div>
                {@html content}
            </div>
        </div>
        <div class="alert-body-action">
            {#if onManage}
                <Button.Action
                    type="button"
                    class="btn-outline btn-sm alert-manage"
                    onclick={onManageWrapper}
                >
                    {onManageText || local.manage[DEFAULT_LANGUAGE]}
                </Button.Action>
            {/if}
            {#if closeable}
                <Button.Basic
                    type="button"
                    class="btn-outline btn-sm alert-close"
                    onclick={dismiss}
                >
                    <Icon name="close" />
                </Button.Basic>
            {/if}
        </div>
    </div>
    {#if details}
        <div class="alert-details">
            <Collapse title="Details" openAtStart={false}>
                <div class="separator"></div>
                {@html details}
            </Collapse>
        </div>
    {/if}
</div>

<style>
    :global {
        .alert {
            color: var(--ink);
            padding: var(--spacing-md);
            border-radius: var(--radius);
            font-size: var(--font-size-sm);
            opacity: 0;
            box-shadow: var(--shadow);
            gap: var(--spacing-sm);
            width: 100%;
            background: var(--glass-strong);
            backdrop-filter: blur(18px) saturate(1.4);
            -webkit-backdrop-filter: blur(18px) saturate(1.4);
            border: 1px solid var(--glass-border);

            &.error {
                border-left: 3px solid #e74c3c;
                color: #c0392b;
            }

            &.warning {
                border-left: 3px solid #f39c12;
                color: #d68910;
            }

            &.info {
                border-left: 3px solid var(--accent);
                color: var(--ink-dim);
            }

            &.success {
                border-left: 3px solid #27ae60;
                color: #1e8449;
            }

            &.show {
                opacity: 1;
                transform: translateX(0);
            }

            & .alert-body {
                display: flex;
                align-items: center;
                justify-content: space-between;

                & .alert-body-text {
                    display: flex;
                    align-items: center;
                    gap: var(--spacing-sm);
                }

                & .alert-icon {
                    margin-bottom: -4px;

                    & svg {
                        width: var(--font-size-xl) !important;
                        height: var(--font-size-xl) !important;
                    }
                }

                & .alert-manage {
                    &:hover { filter: brightness(1.2); }
                    &:active { filter: brightness(0.9); }
                }

                & .alert-close {
                    background: transparent;
                    border: transparent;
                    &:hover { background: var(--glass-strong); }
                }

                & .alert-body-action {
                    display: flex;
                    gap: var(--spacing-sm);
                }
            }

            & .alert-details {
                font-size: var(--font-size-xs);

                & svg {
                    width: var(--font-size-md);
                    height: var(--font-size-md);
                }

                & .collapse-header {
                    padding: var(--spacing-sm) var(--spacing-2xs);
                    padding-bottom: 0;
                    margin-right: var(--spacing-2xs);
                }

                & .collapse-content {
                    padding: var(--spacing-sm) var(--spacing-2xs);
                }

                & .separator {
                    margin-bottom: var(--spacing-sm);
                    background-color: var(--glass-border);
                }
            }
        }
    }
</style>
