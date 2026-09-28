import { combine } from "@/lib/utils";

interface SpinnerProps {
    size?: "small" | "medium" | "large";
    className?: string;
}

const SIZE_CLASSES = {
    small: "spinner small",
    medium: "spinner medium",
    large: "spinner large",
};

export default function Spinner({ size = "small", className }: SpinnerProps) {
    return <small className={combine(SIZE_CLASSES[size], className)} />;
}
