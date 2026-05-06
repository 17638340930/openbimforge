import { redirect } from "next/navigation"

export const runtime = "nodejs"

export default async function Text2BimStatusRedirect({
    searchParams,
}: {
    searchParams: Promise<{ path?: string }>
}) {
    const params = await searchParams
    const suffix = params.path ? `?path=${encodeURIComponent(params.path)}` : ""
    redirect(`/bim/nexus-status${suffix}`)
}
