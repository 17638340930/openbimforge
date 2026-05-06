export interface ClarificationSlot {
    key: string
    labelZh: string
    labelEn: string
    required: boolean
    patterns: RegExp[]
}

export interface ClarificationDecision {
    shouldClarify: boolean
    missingRequiredSlots: string[]
    presentSlots: string[]
    slotSnapshot: ClarificationSlotSnapshot
}

export interface ClarificationSlotSnapshot {
    building_type?: string
    storey_count?: string
    target_area?: string
    floor_height?: string
}

export type ClarifyLanguage = "zh" | "en"
export type GenerationRoute = "nexus-synthesis" | "nexus-visionary"

const BUILDING_TYPE_ALIASES: Array<{
    value: string
    zh: string[]
    en: string[]
}> = [
    { value: "office", zh: ["办公", "写字楼", "办公楼"], en: ["office"] },
    { value: "residential", zh: ["住宅", "居住", "商品房", "小区"], en: ["residential", "housing"] },
    { value: "apartment", zh: ["公寓"], en: ["apartment"] },
    { value: "hospital", zh: ["医院"], en: ["hospital"] },
    { value: "school", zh: ["学校", "教学楼", "校园"], en: ["school", "campus"] },
    { value: "hotel", zh: ["酒店", "宾馆"], en: ["hotel"] },
    { value: "industrial", zh: ["厂房", "工业", "车间"], en: ["industrial", "factory", "workshop"] },
    { value: "mall", zh: ["商场", "商业", "购物中心"], en: ["mall", "commercial"] },
    { value: "villa", zh: ["别墅"], en: ["villa"] },
]

const NEXUS_VISIONARY_HINTS = [
    "草图",
    "图片",
    "参考图",
    "上传图",
    "根据图",
    "从图",
    "零件",
    "机械件",
    "CAD",
    "STL",
    "三维零件",
    "image",
    "sketch",
    "reference image",
    "part",
    "mechanical",
    "layout",
    "stl",
]

const NEXUS_SYNTHESIS_HINTS = [
    "BIM",
    "IFC",
    "建筑",
    "楼",
    "楼层",
    "层高",
    "面积",
    "户型",
    "平面图",
    "办公楼",
    "住宅",
    "医院",
    "building",
    "storey",
    "floor",
    "area",
    "floor height",
    "ifc",
]

const SLOTS: ClarificationSlot[] = [
    {
        key: "building_type",
        labelZh: "建筑类型（住宅/办公/医院等）",
        labelEn: "building type (residential/office/hospital/etc.)",
        required: true,
        patterns: [
            /(住宅|居住|商品房|小区|公寓|办公|写字楼|办公楼|医院|学校|教学楼|酒店|宾馆|厂房|工业|车间|商场|商业|购物中心|别墅)/i,
            /\b(residential|housing|apartment|office|hospital|school|campus|hotel|industrial|factory|workshop|mall|commercial|villa)\b/i,
        ],
    },
    {
        key: "storey_count",
        labelZh: "楼层数",
        labelEn: "number of storeys/floors",
        required: true,
        patterns: [/\b\d+\s*(层|楼|floors?|storeys?)\b/i],
    },
    {
        key: "target_area",
        labelZh: "目标面积",
        labelEn: "target area",
        required: true,
        patterns: [/\b\d+(\.\d+)?\s*(㎡|m2|m²|平方米|square meters?)\b/i],
    },
    {
        key: "floor_height",
        labelZh: "层高",
        labelEn: "typical floor height",
        required: true,
        patterns: [
            /(层高|净高)\s*[:：]?\s*\d+(\.\d+)?\s*(m|米|meter|meters)/i,
            /\b(floor height|storey height)\s*[:：]?\s*\d+(\.\d+)?\s*(m|meter|meters)\b/i,
        ],
    },
]

function matchLast(text: string, pattern: RegExp): RegExpExecArray | null {
    const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`
    const globalPattern = new RegExp(pattern.source, flags)
    const matches = Array.from(text.matchAll(globalPattern))
    return matches.length > 0 ? matches[matches.length - 1] : null
}

function normalizeWhitespace(text: string): string {
    return text.replace(/\s+/g, " ").trim()
}

function normalizeBuildingType(text: string): string | undefined {
    for (const alias of BUILDING_TYPE_ALIASES) {
        const zhMatched = alias.zh.some((token) => text.includes(token))
        const enMatched = alias.en.some((token) => new RegExp(`\\b${token}\\b`, "i").test(text))
        if (zhMatched || enMatched) return alias.value
    }
    return undefined
}

function extractStoreyCount(text: string): string | undefined {
    const match = matchLast(text, /(\d+(?:\.\d+)?)\s*(层|楼|floors?|storeys?)/i)
    return match ? `${match[1]}` : undefined
}

function extractTargetArea(text: string): string | undefined {
    const match = matchLast(text, /(\d+(?:\.\d+)?)\s*(㎡|m2|m²|平方米|square meters?)/i)
    return match ? `${match[1]} m2` : undefined
}

function extractFloorHeight(text: string): string | undefined {
    const explicitMatch = matchLast(text, /(层高|净高|floor height|storey height)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(m|米|meter|meters)/i)
    if (explicitMatch) return `${explicitMatch[2]} m`
    const suffixMatch = matchLast(text, /(\d+(?:\.\d+)?)\s*(m|米)\s*(层高|净高)/i)
    return suffixMatch ? `${suffixMatch[1]} m` : undefined
}

export function inferGenerationRoute(userInputText: string): GenerationRoute {
    const normalized = normalizeWhitespace(userInputText).toLowerCase()
    const hasLayoutHint = NEXUS_VISIONARY_HINTS.some((token) => normalized.includes(token.toLowerCase()))
    const hasBimHint = NEXUS_SYNTHESIS_HINTS.some((token) => normalized.includes(token.toLowerCase()))
    if (hasLayoutHint && !hasBimHint) return "nexus-visionary"
    return "nexus-synthesis"
}

export function extractSlotSnapshot(userInputText: string): ClarificationSlotSnapshot {
    const normalized = normalizeWhitespace(userInputText)
    if (!normalized) return {}
    return {
        building_type: normalizeBuildingType(normalized),
        storey_count: extractStoreyCount(normalized),
        target_area: extractTargetArea(normalized),
        floor_height: extractFloorHeight(normalized),
    }
}

export function mergeSlotSnapshots(...snapshots: Array<ClarificationSlotSnapshot | undefined>): ClarificationSlotSnapshot {
    return snapshots.reduce<ClarificationSlotSnapshot>((acc, snapshot) => {
        if (!snapshot) return acc
        return {
            building_type: snapshot.building_type || acc.building_type,
            storey_count: snapshot.storey_count || acc.storey_count,
            target_area: snapshot.target_area || acc.target_area,
            floor_height: snapshot.floor_height || acc.floor_height,
        }
    }, {})
}

export function getSlotLabel(slotKey: string, language: ClarifyLanguage): string {
    const slot = SLOTS.find((item) => item.key === slotKey)
    if (!slot) return slotKey.replaceAll("_", " ")
    return language === "zh" ? slot.labelZh : slot.labelEn
}

export function formatSlotSnapshot(snapshot: ClarificationSlotSnapshot, language: ClarifyLanguage): string {
    const lines = Object.entries(snapshot)
        .filter(([, value]) => Boolean(value))
        .map(([key, value]) => `- ${getSlotLabel(key, language)}: ${value}`)
    if (lines.length === 0) return language === "zh" ? "暂无已确认参数" : "No confirmed slots yet"
    return lines.join("\n")
}

export function evaluateClarificationNeed(userInputText: string): ClarificationDecision {
    const route = inferGenerationRoute(userInputText)
    const slotSnapshot = extractSlotSnapshot(userInputText)
    if (route === "nexus-visionary") {
        return { shouldClarify: false, missingRequiredSlots: [], presentSlots: ["layout_reference"], slotSnapshot }
    }
    const presentSlots = SLOTS.filter((slot) => {
        const snapshotValue = slotSnapshot[slot.key as keyof ClarificationSlotSnapshot]
        if (snapshotValue) return true
        return slot.patterns.some((pattern) => pattern.test(userInputText))
    }).map((slot) => slot.key)
    const missingRequiredSlots = SLOTS.filter((slot) => {
        if (!slot.required) return false
        const snapshotValue = slotSnapshot[slot.key as keyof ClarificationSlotSnapshot]
        return !snapshotValue
    }).map((slot) => slot.key)
    return { shouldClarify: missingRequiredSlots.length > 0, missingRequiredSlots, presentSlots, slotSnapshot }
}

export function buildFallbackClarificationText(missingRequiredSlots: string[], language: ClarifyLanguage, snapshot?: ClarificationSlotSnapshot): string {
    const items = missingRequiredSlots.map((slotKey, index) => `${index + 1}. ${getSlotLabel(slotKey, language)}`)
    const knownSummary = snapshot ? formatSlotSnapshot(snapshot, language) : language === "zh" ? "暂无已确认参数" : "No confirmed slots yet"
    if (language === "zh") {
        return [
            "在发起 Nexus 协同合成之前，还需要明确以下核心参数：",
            `当前已捕获：\n${knownSummary}`,
            "请补充：",
            ...items,
            "您可以直接回复，例如：办公楼，6层，4200㎡，层高3.6m。",
        ].join("\n")
    }
    return ["Before I initiate Nexus Synthesis, I still need a few required parameters.", `Currently confirmed:\n${knownSummary}`, "Please provide:", ...items, "Example: office building, 6 floors, 4200 m2, floor height 3.6 m."].join("\n")
}

export function buildClarificationPrompt(userInputText: string, missingRequiredSlots: string[], language: ClarifyLanguage, snapshot?: ClarificationSlotSnapshot): string {
    const missingText = missingRequiredSlots.map((slotKey) => `- ${getSlotLabel(slotKey, language)}`).join("\n")
    const knownSummary = snapshot ? formatSlotSnapshot(snapshot, language) : language === "zh" ? "暂无已确认参数" : "No confirmed slots yet"
    if (language === "zh") {
        return [
            "你是 Nexus-Orchestrator 的 BIM 参数追问助手。",
            "目标：针对缺失的必填项生成精炼追问，体现学术严谨性，避免重复确认已捕获的信息。",
            "规则：",
            "1) 仅针对缺失参数发起确认。",
            "2) 简要说明当前 Nexus 状态，再列出待明确项。",
            "3) 语气专业、干练。",
            "4) 给出一条短示例。",
            "5) 用中文回答。",
            "",
            `当前已捕获参数：\n${knownSummary}`,
            "",
            `用户原始输入：\n${userInputText}`,
            "",
            `缺失关键字段：\n${missingText}`,
        ].join("\n")
    }
    return ["You are the Nexus-Orchestrator BIM parameter clarification assistant.", "Generate concise follow-up questions for missing fields while maintaining academic rigor.", "Rules:", "1) Ask for missing fields only.", "2) State current orchestration status briefly.", "3) Professional and concise tone.", "4) Include one short example answer.", "5) Respond in English.", "", `Currently confirmed slots:\n${knownSummary}`, "", `User input:\n${userInputText}`, "", `Missing required fields:\n${missingText}`].join("\n")
}

export function buildReadinessStatusText(language: ClarifyLanguage, completionScore: number, routeSuggestion: GenerationRoute, snapshot: ClarificationSlotSnapshot): string {
    const slotSummary = formatSlotSnapshot(snapshot, language)
    const routeLabel =
        routeSuggestion === "nexus-visionary"
            ? language === "zh" ? "Nexus-Visionary（视觉拓扑转化）" : "Nexus-Visionary (Visual Topology Interpretation)"
            : language === "zh" ? "Nexus-Architect → Nexus-Constructor（协同合成）" : "Nexus-Architect -> Nexus-Constructor (Collaborative Synthesis)"
    if (language === "zh") {
        return [`需求整备完成度：${completionScore}/100`, `当前判断：已满足合成条件，建议执行 ${routeLabel} 链路。`, `已确认参数：\n${slotSummary}`, "现在进入 Constructive Synthesis 阶段。"].join("\n")
    }
    return [`Readiness score: ${completionScore}/100`, `Status: requirements are sufficient. Suggested route: ${routeLabel}.`, `Confirmed slots:\n${slotSummary}`, "Proceeding to Constructive Synthesis phase."].join("\n")
}