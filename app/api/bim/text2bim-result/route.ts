/**
 * @deprecated Legacy Text2BIM compatibility route.
 * Keep until old Vectorworks/Web Palette clients stop calling /api/bim/text2bim-result.
 * New clients should use /api/bim/forge-architect-result.
 */
export { GET, runtime } from "../forge-architect-result/route"
