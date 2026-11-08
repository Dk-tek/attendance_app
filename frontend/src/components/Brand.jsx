export function Brand({ compact = false }) {
  return <span className={`fieldBrand ${compact ? "compactBrand" : ""}`}><span className="brandLogo"><img src={`${import.meta.env.BASE_URL}field-pixel-logo.png`} alt="Field Pixel logo" /></span>{!compact ? <span className="brandWordmark">Field Pixel<span>CLARITY IN EVERY CHECK-IN</span></span> : null}</span>;
}
