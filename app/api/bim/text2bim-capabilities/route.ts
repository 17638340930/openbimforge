/**
 * @deprecated Legacy Text2BIM compatibility route.
 * Keep until old Vectorworks/Web Palette clients stop calling /api/bim/text2bim-capabilities.
 * New clients should use /api/bim/forge-architect-capabilities.
 */
export { GET, runtime } from "../forge-architect-capabilities/route"
