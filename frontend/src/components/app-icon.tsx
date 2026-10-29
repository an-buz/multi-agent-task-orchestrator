export function AppIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 64 64" fill="none">
      <path
        d="M16 32C32 32 32 16 48 16M16 32C32 32 32 48 48 48"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <g fill="currentColor">
        <circle cx="16" cy="32" r="7" />
        <circle cx="48" cy="16" r="7" />
        <circle cx="48" cy="48" r="7" />
      </g>
    </svg>
  );
}
