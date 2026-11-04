/**
 * Hero illustration: a schematic of Zimbabwe's main highways with the Harare to Mutare route (A3) lit.
 * Inline SVG, no tiles, no network: it costs a few hundred bytes and works on any connection.
 * It is decoration only and shows no incidents, so it can never be mistaken for live data.
 */
export function RouteArt({ className }: { className?: string }) {
  const road = "M430 170 L380 192 L335 215 L318 262 L332 300 L250 345 M430 170 L440 235 L470 360 L440 430 L410 480 M250 345 L330 420 L410 480 M430 170 L400 110 L380 50";
  return (
    <div className={className}>
      <svg viewBox="320 100 400 340" preserveAspectRatio="xMidYMid slice" className="size-full" aria-hidden focusable="false">
        <rect x="0" y="0" width="800" height="520" fill="#1e293b" />
        <path d="M0 410 C120 380 200 430 320 405 S540 340 800 390 V520 H0Z" fill="#182235" />
        <path d="M0 90 C140 130 230 70 370 108 S620 50 800 98" fill="none" stroke="#1d4f6e" strokeWidth="12" strokeLinecap="round" opacity=".55" />
        <g fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d={road} stroke="#0f172a" strokeWidth="9" />
          <path d={road} stroke="#475569" strokeWidth="4" />
          <path d="M430 170 L490 185 L580 210 L650 240" stroke="#0f172a" strokeWidth="13" />
          <path d="M430 170 L490 185 L580 210 L650 240" stroke="#34d399" strokeWidth="6" />
        </g>
        <g fill="#94a3b8">
          <circle cx="332" cy="300" r="3.5" />
          <circle cx="470" cy="360" r="3.5" />
          <circle cx="580" cy="210" r="3.5" />
        </g>
        <g fontFamily="Inter, sans-serif" fontWeight="700" fontSize="13" fill="#cbd5e1" stroke="#1e293b" strokeWidth="3.5" paintOrder="stroke">
          <text x="342" y="304">Gweru</text>
          <text x="482" y="366">Masvingo</text>
          <text x="440" y="236">Chivhu</text>
          <text x="586" y="204">Rusape</text>
        </g>
        <circle cx="430" cy="170" r="10" fill="#0f172a" stroke="#34d399" strokeWidth="5" />
        <circle cx="650" cy="240" r="10" fill="#0f172a" stroke="#f8fafc" strokeWidth="5" />
        <g fontFamily="Inter, sans-serif" fontWeight="800" fontSize="16" fill="#f8fafc" stroke="#1e293b" strokeWidth="4" paintOrder="stroke">
          <text x="400" y="150">Harare</text>
          <text x="632" y="272">Mutare</text>
        </g>
      </svg>
    </div>
  );
}
