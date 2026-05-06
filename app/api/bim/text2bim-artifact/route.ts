/**
 * @deprecated Legacy Text2BIM compatibility route.
 * Keep until old Vectorworks/Web Palette clients stop calling /api/bim/text2bim-artifact.
 * New clients should use /api/bim/forge-architect-artifact.
 */
export { GET, runtime } from "../forge-architect-artifact/route"
