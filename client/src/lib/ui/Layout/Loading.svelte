<script lang="ts">
    import { Spinner } from "$lib/ui/Components/Loader";
</script>

<div class="w-full h-full flex items-center justify-center">
    <div class="flex flex-col items-center gap-4 bg-white dark:bg-[#1e1e1e] border border-notion-border dark:border-notion-border-dark rounded-xl shadow-lg px-8 py-8">
        <Spinner size="medium"/>
        <h3 class="text-sm text-notion-text-muted">Connecting to accounts...</h3>
    </div>
</div>
