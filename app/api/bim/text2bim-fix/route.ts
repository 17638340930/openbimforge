/**
 * @deprecated Legacy Text2BIM compatibility route.
 * Keep until old Vectorworks/Web Palette clients stop calling /api/bim/text2bim-fix.
 * New clients should use /api/bim/forge-architect-fix.
 */
export { POST, runtime } from "../forge-architect-fix/route"
