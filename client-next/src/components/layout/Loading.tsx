import Spinner from "@/components/Loader/Spinner";

export default function Loading() {
    return (
        <div className="w-full h-full flex items-center justify-center">
            <div className="flex flex-col items-center gap-4 bg-notion-surface border border-notion-border rounded-xl shadow-notion-float px-8 py-8">
                <Spinner size="medium" />
                <h3 className="text-sm text-notion-text-muted">Connecting to accounts...</h3>
            </div>
        </div>
    );
}
