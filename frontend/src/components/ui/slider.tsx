import * as RadixSlider from "@radix-ui/react-slider";

type SliderProps = {
  value: number;
  min: number;
  max: number;
  step: number;
  onValueChange: (value: number) => void;
  "aria-label": string;
};

export function Slider({
  value,
  min,
  max,
  step,
  onValueChange,
  "aria-label": ariaLabel,
}: SliderProps) {
  return (
    <RadixSlider.Root
      aria-label={ariaLabel}
      min={min}
      max={max}
      step={step}
      value={[value]}
      onValueChange={([nextValue]) => {
        if (nextValue !== undefined) onValueChange(nextValue);
      }}
      className="relative flex h-5 w-full touch-none select-none items-center"
    >
      <RadixSlider.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-slate-800">
        <RadixSlider.Range className="absolute h-full rounded-full bg-emerald-500" />
      </RadixSlider.Track>
      <RadixSlider.Thumb className="block size-4 rounded-full border-2 border-(--surface) bg-emerald-500 shadow outline-none transition focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:ring-offset-(--surface)" />
    </RadixSlider.Root>
  );
}
