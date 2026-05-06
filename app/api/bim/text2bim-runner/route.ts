/**
 * @deprecated Legacy Text2BIM compatibility route.
 * Keep until old Vectorworks/Web Palette clients stop calling /api/bim/text2bim-runner.
 * New clients should use /api/bim/forge-architect-runner.
 */
export { GET, runtime } from "../forge-architect-runner/route"
