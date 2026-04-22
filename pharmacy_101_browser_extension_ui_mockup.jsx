import React from "react";

export default function Pharmacy101ExtensionMockup() {
  const seedCases = [
    {
      title: "Levofloxacin 750 mg",
      lane: "CHALLENGE",
      sig: "take 1 tablet by mouth daily",
      qty: 21,
      structural: "Quantity implies a 21-day course, which exceeds common short-course context for this agent.",
      affects: "duration",
      clarification: "Likely",
      resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
      refresh: [
        "Common pattern: Fluoroquinolone therapy is typically ordered for defined, short-course treatment windows.",
        "Why this stands out: A 21-day supply at once daily implies a course length that warrants active confirmation.",
        "Why quantity matters: Extended fluoroquinolone use carries safety considerations that make intended duration critical to confirm."
      ],
      message: "Quantity implies a 21-day course. Please confirm whether that duration is intended, or whether a shorter course was planned.",
    },
    {
      title: "Valacyclovir 1 gm",
      lane: "CHALLENGE",
      sig: "take 1 tablet by mouth every 12 hours",
      qty: 28,
      structural: "Quantity implies a 14-day course, which may not align with a short-course pattern.",
      affects: "duration",
      clarification: "Likely",
      resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
      refresh: [
        "Common pattern: These orders commonly include a clearly defined treatment window.",
        "Why this stands out: Quantity implies a course length that should be actively confirmed, not simply filled in.",
        "Why quantity matters: Quantity drives total exposure and can create a longer course than intended."
      ],
      message: "Quantity implies a 14-day course at current directions. Please confirm whether that implied duration matches intended use.",
    },
    {
      title: "Ubrelvy 50 mg",
      lane: "CLARIFY USE",
      sig: "take 1 tablet by mouth daily as needed",
      qty: 10,
      structural: "PRN use is present, but a maximum daily dose is not stated.",
      affects: "instructions",
      clarification: "Likely",
      resolution: { label: "CLARIFY USE", emoji: "🟠", bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-900" },
      refresh: [
        "Common pattern: This type of PRN therapy is often paired with a defined dosing limit.",
        "Why this stands out: The instruction leaves the upper use boundary unstated.",
        "Why quantity matters: Quantity does not define the maximum intended use in one day."
      ],
      message: "PRN use is listed, but a maximum daily dose is not stated on the original order. Please clarify intended maximum.",
    },
    {
      title: "Lisinopril 20 mg",
      lane: "VERIFY AS ENTERED",
      sig: "take 1 tablet by mouth daily",
      qty: 30,
      structural: "No obvious structural issue detected.",
      affects: "none",
      clarification: "Unlikely",
      resolution: { label: "NONE", emoji: "🟢", bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-900" },
      refresh: [
        "No pattern issue surfaced from the current structure.",
      ],
      message: "No message needed.",
    },
  ];

  const seededCases = React.useMemo(
    () => seedCases.map((item, index) => ({ ...item, id: item.id || `seed-${index}` })),
    []
  );
  const nextCaseIdRef = React.useRef(seededCases.length);
  const seededStatuses = React.useMemo(
    () => Object.fromEntries(seededCases.map((item) => [item.id, "active"])),
    [seededCases]
  );

  const [cases, setCases] = React.useState(seededCases);
  const [caseStatuses, setCaseStatuses] = React.useState(seededStatuses);
  const [activeCaseId, setActiveCaseId] = React.useState(seededCases[0]?.id || null);
  const [prescriptionInput, setPrescriptionInput] = React.useState("");
  const [sourceRefInput, setSourceRefInput] = React.useState("");
  const [inputFeedback, setInputFeedback] = React.useState(null);
  const [interpretedAsText, setInterpretedAsText] = React.useState("");
  const [auditCount, setAuditCount] = React.useState(0);
  const [isExportingAudit, setIsExportingAudit] = React.useState(false);
  const [notesById, setNotesById] = React.useState({});
  const [sourceRefById, setSourceRefById] = React.useState({});
  const [pendingSubStatus, setPendingSubStatus] = React.useState({});
  const [pendingOriginById, setPendingOriginById] = React.useState({});
  const [pendingMovedAtById, setPendingMovedAtById] = React.useState({});
  const active = cases.find((item) => item.id === activeCaseId) || cases[0] || null;
  const activeStatus = caseStatuses[active?.id] || "active";

  React.useEffect(() => {
    if (!cases.length) {
      if (activeCaseId !== null) setActiveCaseId(null);
      return;
    }

    const hasActiveCase = activeCaseId && cases.some((item) => item.id === activeCaseId);
    if (!hasActiveCase) {
      setActiveCaseId(cases[0].id);
    }
  }, [cases, activeCaseId]);

  const refreshAuditMeta = React.useCallback(async () => {
    try {
      const response = await fetch("http://localhost:8000/audit/meta");
      if (!response.ok) {
        setAuditCount(0);
        return;
      }
      const data = await response.json();
      setAuditCount(Number(data?.total || 0));
    } catch (err) {
      setAuditCount(0);
    }
  }, []);

  React.useEffect(() => {
    refreshAuditMeta();
  }, [refreshAuditMeta]);

  const handleExportAuditLog = async () => {
    if (isExportingAudit || auditCount <= 0) return;
    setIsExportingAudit(true);
    try {
      const response = await fetch("http://localhost:8000/audit/export.csv");
      if (!response.ok) {
        throw new Error("Export failed");
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      link.href = downloadUrl;
      link.download = `pharmacy101_audit_log_${stamp}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setInputFeedback({ type: "invalid", message: "Could not export audit log." });
    } finally {
      setIsExportingAudit(false);
    }
  };

  const HIGH_RISK_PRN_DRUGS = [
    "sumatriptan",
    "rizatriptan",
    "warfarin",
    "insulin",
    "oxycodone",
    "lorazepam",
  ];

  const hasHighRiskPrnDrug = (rawText = "") => {
    const normalizedDrugLine = String(rawText)
      .split(/\r?\n/)[0]
      .toLowerCase();
    return HIGH_RISK_PRN_DRUGS.some((drug) => normalizedDrugLine.includes(drug));
  };

  const KNOWN_DRUG_NAMES = [
    "levofloxacin",
    "valacyclovir",
    "ubrelvy",
    "lisinopril",
    "colchicine",
    "zolpidem",
    "sumatriptan",
    "rizatriptan",
    "warfarin",
    "insulin",
    "oxycodone",
    "lorazepam",
    "ondansetron",
  ];

  const editDistance = (a = "", b = "") => {
    const s = a.toLowerCase();
    const t = b.toLowerCase();
    const dp = Array.from({ length: s.length + 1 }, () => Array(t.length + 1).fill(0));

    for (let i = 0; i <= s.length; i += 1) dp[i][0] = i;
    for (let j = 0; j <= t.length; j += 1) dp[0][j] = j;

    for (let i = 1; i <= s.length; i += 1) {
      for (let j = 1; j <= t.length; j += 1) {
        const cost = s[i - 1] === t[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + cost,
        );
      }
    }

    return dp[s.length][t.length];
  };

  const normalizeSigText = (rawSig = "") => {
    let sig = rawSig.toLowerCase();
    sig = sig.replace(/\bdaliy\b/g, "daily");
    sig = sig.replace(/\bnigtly\b/g, "nightly");
    sig = sig.replace(/\bpo\b/g, "by mouth");
    sig = sig.replace(/\bqhs\b/g, "nightly");
    sig = sig.replace(/\bbid\b/g, "twice daily");
    sig = sig.replace(/\bprn\b/g, "as needed");
    sig = sig.replace(/\b1\s*t\b/g, "1 tablet");
    sig = sig.replace(/\btab\b/g, "tablet");
    if (/^\d+(?:\.\d+)?\s+(tablet|capsule|puff|drop|ml|spray)\b/.test(sig)) {
      sig = `take ${sig}`;
    }
    sig = sig.replace(/\s+/g, " ").trim();
    return sig;
  };

  const normalizeDrugChunk = (rawDrug = "") => {
    const correctionNotes = [];
    let drug = rawDrug.toLowerCase().replace(/\s+/g, " ").trim();
    drug = drug.replace(/\s*\([^)]*\)\s*/g, " ").replace(/\s+/g, " ").trim();

    const tokenMatch = drug.match(/^[a-z]+/i);
    const firstToken = tokenMatch ? tokenMatch[0].toLowerCase() : "";

    if (!firstToken) {
      return {
        ok: false,
        error: "Could not reliably identify the drug name.",
        expected: "Drug: <name + strength>",
      };
    }

    if (!KNOWN_DRUG_NAMES.includes(firstToken)) {
      const ranked = KNOWN_DRUG_NAMES
        .map((name) => ({ name, distance: editDistance(firstToken, name) }))
        .sort((a, b) => a.distance - b.distance);

      const best = ranked[0];
      const second = ranked[1];
      const confident = best && best.distance <= 2 && (!second || second.distance - best.distance >= 1);

      if (!confident) {
        return {
          ok: false,
          error: "Could not reliably identify the drug name.",
          expected: "Drug: <name + strength>",
        };
      }

      drug = drug.replace(new RegExp(`^${firstToken}`), best.name);
      correctionNotes.push(`Drug normalized: ${firstToken} -> ${best.name}`);
    }

    return {
      ok: true,
      value: drug,
      correctionNotes,
    };
  };

  const getActionText = (item) => {
    if (item?.pattern_assessment === "Pattern-questionable") return "Clarify Intended Use";
    if (item.lane === "CHALLENGE") return "Clarify Duration";
    if (item.lane === "CLARIFY USE") return "Clarify Patient Use";
    if (item.lane === "COMPLETE") return "Complete Missing Detail";
    return "Verify As Entered";
  };

  const getShortActionPhrase = (item, status = "active", caseId = null) => {
    if (status === "pending") return pendingSubStatus[caseId] || "Awaiting MD response";
    if (status === "resolved") {
      if (["VERIFY AS ENTERED", "NONE"].includes(item.lane)) return "Verify as entered";
      return "Resolved";
    }

    const structural = (item?.structural || "").toLowerCase();

    if (item?.pattern_assessment === "Pattern-questionable") {
      return "Clarify intended use";
    }

    if (item.lane === "CHALLENGE") {
      if (structural.includes("total dose") || structural.includes("strength") || structural.includes("dose/strength")) {
        return "Clarify total dose";
      }
      if (structural.includes("max") && structural.includes("dose")) return "Clarify max dose";
      if (structural.includes("course") || structural.includes("duration") || structural.includes("extended")) {
        return "Confirm course length";
      }
      return "Clarify duration";
    }

    if (["CLARIFY USE", "COMPLETE"].includes(item.lane)) {
      if (structural.includes("schedule")) return "Confirm schedule";
      if (structural.includes("pattern") || structural.includes("prn") || structural.includes("use")) {
        return "Clarify use pattern";
      }
      return "Clarify use";
    }

    return "Verify as entered";
  };

  const getDisposition = (item, status, caseId = null) => {
    if (status === "pending") {
      const pendingOrigin = caseId ? pendingOriginById[caseId] : null;
      if (pendingOrigin) {
        return {
          text: pendingOrigin.disposition,
          color: pendingOrigin.color,
        };
      }
      return null;
    }
    if (status === "resolved") return null;
    if (item?.pattern_assessment === "Pattern-questionable") {
      return { text: "Can verify, but follow-up on intended use is recommended", color: "text-amber-700" };
    }
    if (item.lane === "CHALLENGE") return { text: "Do not dispense until clarified", color: "text-red-700" };
    if (["CLARIFY USE", "COMPLETE"].includes(item.lane)) {
      return { text: "Can dispense, but clarification recommended", color: "text-amber-700" };
    }
    return { text: "Safe to verify as entered", color: "text-emerald-700" };
  };

  const getPendingOriginMeta = (item) => {
    if (!item) return null;

    if (item?.pattern_assessment === "Pattern-questionable") {
      return {
        lane: "VERIFY",
        subStatus: "Awaiting follow-up",
        disposition: "Can verify while awaiting response",
        color: "text-amber-700",
      };
    }

    if (item.lane === "CHALLENGE") {
      return {
        lane: "HOLD",
        subStatus: "Awaiting MD response",
        disposition: "Do not dispense until clarified",
        color: "text-red-700",
      };
    }

    if (["CLARIFY USE", "COMPLETE"].includes(item.lane)) {
      return {
        lane: "ADDRESS",
        subStatus: "Awaiting clarification",
        disposition: "Can verify while awaiting response",
        color: "text-amber-700",
      };
    }

    return {
      lane: "VERIFY",
      subStatus: "Awaiting follow-up",
      disposition: "Safe to verify while awaiting response",
      color: "text-emerald-700",
    };
  };

  const getQueueSignal = (item) => {
    if (item?.pattern_assessment === "Pattern-questionable") return { label: "VERIFY - FOLLOW-UP", tone: "amber" };
    if (item.lane === "CHALLENGE") return { label: "HOLD NOW", tone: "red" };
    if (["CLARIFY USE", "COMPLETE"].includes(item.lane)) return { label: "ADDRESS DURING WORKFLOW", tone: "amber" };
    return { label: "VERIFY", tone: "green" };
  };

  const getVisibleHeaderState = (item, status) => {
    if (status === "pending") {
      return {
        label: "PENDING",
        tone: "yellow",
        bg: "bg-yellow-50",
        border: "border-yellow-300",
        text: "text-yellow-900",
      };
    }

    if (status === "resolved") {
      return {
        label: "RESOLVED",
        tone: "green",
        bg: "bg-emerald-50",
        border: "border-emerald-300",
        text: "text-emerald-900",
      };
    }

    const queueSignal = getQueueSignal(item);
    return {
      label: queueSignal.label,
      tone: queueSignal.tone,
      bg: item.resolution.bg,
      border: item.resolution.border,
      text: item.resolution.text,
    };
  };

  const getConfidenceMeta = (item, status = "active") => {
    if (!item || status === "pending" || status === "resolved") return null;

    const lane = item.lane;

    // VERIFY — no confidence displayed
    if (lane === "VERIFY AS ENTERED" || lane === "NONE") return null;

    const structural = (item.structural || "").toLowerCase();

    // Boolean flags derived from structural text and item properties
    const contradiction       = /conflict|cannot be followed|does not match|mismatch/.test(structural);
    const not_followable      = structural.includes("cannot be followed");
    const high_impact_missing = (
      /exposure|stop-point|duration|maximum|not stated/.test(structural) ||
      item.affects === "duration"
    );
    const minor_issue         = structural.includes("minor");
    const borderline_hold     = (lane === "CLARIFY USE" || lane === "COMPLETE") && item.affects === "duration";

    if (item?.pattern_assessment === "Pattern-questionable") {
      return {
        level: "MEDIUM",
        className: "border-amber-200 bg-amber-50 text-amber-600 font-medium",
        style: { opacity: 0.88 },
      };
    }

    // HOLD lane (CHALLENGE) — red palette
    // HIGH: contradiction, not followable, or high-impact missing | bold, full opacity
    // MEDIUM: still HOLD but less clearly critical     | medium weight, ~85% opacity
    // LOW: not used for HOLD
    if (lane === "CHALLENGE") {
      const isHigh = contradiction || not_followable || high_impact_missing;
      const level = isHigh ? "HIGH" : "MEDIUM";
      return {
        level,
        className: level === "HIGH"
          ? "border-red-300 bg-red-50 text-red-700 font-bold"
          : "border-red-200 bg-red-50 text-red-600 font-medium",
        style: level === "HIGH" ? { opacity: 1 } : { opacity: 0.85 },
      };
    }

    // ADDRESS lane (CLARIFY USE, COMPLETE) — amber palette
    // HIGH: borderline-hold concern             | bold, full opacity
    // MEDIUM: clear need for clarification      | medium weight, ~88% opacity
    // LOW: minor issue / low-risk ambiguity     | normal weight, ~65% opacity
    if (lane === "CLARIFY USE" || lane === "COMPLETE") {
      const level = borderline_hold ? "HIGH"
                  : minor_issue     ? "LOW"
                  : "MEDIUM";
      return {
        level,
        className: level === "HIGH"   ? "border-amber-300 bg-amber-50 text-amber-700 font-bold"
                 : level === "MEDIUM" ? "border-amber-200 bg-amber-50 text-amber-600 font-medium"
                 :                      "border-amber-200 bg-white text-amber-500 font-normal",
        style: level === "HIGH"   ? { opacity: 1 }
             : level === "MEDIUM" ? { opacity: 0.88 }
             :                      { opacity: 0.65 },
      };
    }

    return null;
  };

  const getDebugLaneSummary = (item, status) => {
    const fastLane = preclassifyLane(`${item.title}\n${item.sig}`, item.sig, Number(item.qty));
    if (status === "pending") return `Fast Lane: ${fastLane} | Final Lane: PENDING`;
    if (status === "resolved") return `Fast Lane: ${fastLane} | Final Lane: RESOLVED`;

    const queueLane = getQueueSignal(item).label;
    const finalLane = queueLane === "HOLD NOW"
      ? "HOLD"
      : queueLane === "ADDRESS DURING WORKFLOW"
        ? "ADDRESS"
        : "VERIFY";

    return `Fast Lane: ${fastLane} | Final Lane: ${finalLane}`;
  };

  const getPrimaryMessage = (item) => {
    const issueLine = String(item?.issue_line || "").trim();
    const actionLine = String(item?.action_line || "").trim();
    const whyThisMatters = String(item?.why_this_matters || "").trim();

    if (issueLine && actionLine) return `${issueLine}. ${actionLine}`;
    if (actionLine) return actionLine;
    if (issueLine) return issueLine;
    if (whyThisMatters) return whyThisMatters;

    const fullMessage = String(item?.message || "").trim();
    if (!fullMessage || fullMessage === "No message needed.") return "No action needed.";

    const firstSentence = fullMessage.split(/[.!?]/)[0].trim();
    return firstSentence ? `${firstSentence}.` : fullMessage;
  };

  const getFirstSentence = (value) => {
    const text = String(value || "").trim();
    if (!text) return "";
    const match = text.match(/^(.+?[.!?])(?:\s|$)/);
    return (match ? match[1] : text).trim();
  };

  const stripReasonPrefix = (value) => {
    const text = String(value || "").trim();
    if (!text) return "";
    return text
      .replace(/^Step\s*\d+[^:]*:\s*/i, "")
      .replace(/^(Pattern focus|Common pattern|Why this matters|Why this stands out|Next step):\s*/i, "")
      .trim();
  };

  const getRefreshLineByPrefix = (item, prefixes = []) => {
    const lines = Array.isArray(item?.refresh) ? item.refresh : [];
    const normalizedPrefixes = prefixes.map((p) => String(p || "").toLowerCase());
    const match = lines.find((line) => {
      const lower = String(line || "").toLowerCase();
      return normalizedPrefixes.some((prefix) => lower.startsWith(prefix));
    });
    return stripReasonPrefix(match || "");
  };

  const getPrimaryActionInstruction = (item, status = "active", caseId = null) => {
    const laneLabel = getVisibleHeaderState(item, status).label;
    if (status === "pending") return pendingSubStatus[caseId] || "Awaiting prescriber response before next step.";
    if (status === "resolved") return "Action completed. Continue workflow based on resolved direction.";
    if (laneLabel === "HOLD NOW") return "Confirm the contradictory or unsafe directions with prescriber before dispensing.";
    if (laneLabel === "VERIFY - FOLLOW-UP") return "Verify as entered and follow up on the intended use or treatment plan.";
    if (laneLabel === "ADDRESS DURING WORKFLOW") return "Clarify missing use boundaries during workflow and document response.";
    return "Verify as entered and continue standard dispensing workflow.";
  };

  const getSupportingContextLine = (item) => {
    const issueLine = String(item?.issue_line || "").trim();
    if (issueLine) return getFirstSentence(issueLine);
    const structural = String(item?.structural || "").trim();
    if (structural) return getFirstSentence(structural);
    return "No structural discrepancy detected.";
  };

  const getQuickRationale = (item) => {
    const isVerifyLane = ["VERIFY AS ENTERED", "NONE"].includes(String(item?.lane || "").toUpperCase());

    const typical = getRefreshLineByPrefix(item, ["pattern focus:", "common pattern:"]) ||
      (isVerifyLane
        ? "Directions are followable and structurally complete for routine verification."
        : "Expected pattern includes clear boundaries for dose, duration, and use triggers.");

    const deviation = getRefreshLineByPrefix(item, ["why this stands out:"]) ||
      getFirstSentence(String(item?.issue_line || "").trim()) ||
      getFirstSentence(String(item?.structural || "").trim()) ||
      (isVerifyLane
        ? "No meaningful deviation detected in the entered directions."
        : "Current directions leave a key use boundary unclear.");

    const risk = getRefreshLineByPrefix(item, ["why this matters:"]) ||
      getFirstSentence(String(item?.override_risk || "").trim()) ||
      (isVerifyLane
        ? "Low immediate risk when verified as entered."
        : "Unclear intent can lead to incorrect duration or unsafe total exposure.");

    return { typical, deviation, risk };
  };

  const getToneDotClass = (tone) => {
    if (tone === "red") return "bg-red-500";
    if (tone === "amber") return "bg-amber-500";
    if (tone === "yellow") return "bg-yellow-500";
    if (tone === "slate") return "bg-slate-400";
    return "bg-emerald-500";
  };

  const getQueueDrugName = (item) => {
    const duplicateCount = cases.filter((x) => x.title === item.title).length;
    if (duplicateCount <= 1) return item.title;

    const sigLower = item.sig.toLowerCase();
    const context = sigLower.includes("prn") || sigLower.includes("as needed") ? "PRN" : "Scheduled";
    return `${item.title} — ${context}`;
  };

  const getPatternTemplate = (patternKey) => {
    const templates = {
      "prn-use-unclear": {
        title: "Pattern: PRN Use Unclear",
        lane: "CHALLENGE",
        sig: "[paste or type SIG]",
        qty: "[enter qty]",
        sourceRef: "",
        structural: "PRN use is present, but a treatment window or episode-based instruction is not stated.",
        affects: "instructions",
        clarification: "Likely",
        resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
        refresh: [
          "Pattern focus: PRN medication instructions should specify use conditions and treatment windows.",
          "Why this matters: Patient-facing use structure must be clear for safe self-administration.",
          "Next step: Confirm with prescriber the intended use window and episode-based instructions."
        ],
        message: "PRN instructions are present but lack a clear treatment window. Please provide clarification on how this PRN medication is intended to be used.",
      },
      "extended-duration-mismatch": {
        title: "Pattern: Extended Duration Mismatch",
        lane: "CHALLENGE",
        sig: "[paste or type SIG]",
        qty: "[enter qty]",
        sourceRef: "",
        structural: "Quantity implies a course length that exceeds typical short-course context for this medication type.",
        affects: "duration",
        clarification: "Likely",
        resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
        refresh: [
          "Pattern focus: Extended-use medications require explicit duration confirmation.",
          "Why this matters: Longer courses carry cumulative safety considerations.",
          "Next step: Confirm with prescriber whether the extended quantity was intentional."
        ],
        message: "Quantity implies an extended course duration. Please confirm whether this longer duration is intended for the patient.",
      },
      "scheduled-vs-prn-conflict": {
        title: "Pattern: Scheduled vs PRN Conflict",
        lane: "CHALLENGE",
        sig: "[paste or type SIG]",
        qty: "[enter qty]",
        sourceRef: "",
        structural: "Combined daily and PRN directions are present, but use boundaries and triggers are not explicit.",
        affects: "instructions",
        clarification: "Likely",
        resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
        refresh: [
          "Pattern focus: Mixed scheduled and PRN instructions must separate baseline use from breakthrough use.",
          "Why this matters: Patients need clear boundaries between routine and as-needed dosing.",
          "Next step: Clarify which portion is daily maintenance and which is PRN."
        ],
        message: "Instructions mix scheduled and PRN use without clear boundaries. Please clarify the intended baseline dose and PRN use conditions.",
      },
      "missing-max-dose": {
        title: "Pattern: Missing Max Dose",
        lane: "CLARIFY USE",
        sig: "[paste or type SIG]",
        qty: "[enter qty]",
        sourceRef: "",
        structural: "PRN use is present, but a maximum daily dose is not stated.",
        affects: "instructions",
        clarification: "Likely",
        resolution: { label: "CLARIFY USE", emoji: "🟠", bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-900" },
        refresh: [
          "Pattern focus: PRN dosing should always include a stated maximum daily limit.",
          "Why this matters: Uncontrolled PRN dosing can exceed safe daily totals.",
          "Next step: Confirm the intended maximum daily dose with the prescriber."
        ],
        message: "PRN use is listed without a stated maximum daily dose. Please specify the intended maximum dose per day.",
      },
      "duration-quantity-mismatch": {
        title: "Pattern: Duration Quantity Mismatch",
        lane: "CHALLENGE",
        sig: "[paste or type SIG]",
        qty: "[enter qty]",
        sourceRef: "",
        structural: "Quantity implies a course length that may not align with intended treatment duration.",
        affects: "duration",
        clarification: "Likely",
        resolution: { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" },
        refresh: [
          "Pattern focus: Quantity and directions should align with a clearly stated course duration.",
          "Why this matters: Misaligned quantities can create unintended treatment gaps or overages.",
          "Next step: Confirm the intended treatment duration matches the supplied quantity."
        ],
        message: "Quantity does not clearly align with the stated or implied treatment duration. Please confirm the intended course length.",
      },
    };
    return templates[patternKey] || null;
  };

  const addCaseAndSelect = (nextCase, sourceRef = "") => {
    if (!nextCase) return;
    const caseWithId = { ...nextCase, id: nextCase.id || `case-${nextCaseIdRef.current++}` };
    setCases((prev) => {
      return [...prev, caseWithId];
    });
    setActiveCaseId(caseWithId.id);
    setCaseStatuses((prev) => ({ ...prev, [caseWithId.id]: "active" }));
    setSourceRefById((prev) => ({ ...prev, [caseWithId.id]: sourceRef }));
  };

  const loadQuickAction = (patternKey) => {
    const patternTemplate = getPatternTemplate(patternKey);
    addCaseAndSelect(patternTemplate);
  };

  const preclassifyLane = (rawText, sig, qty) => {
    const textLower = (rawText || "").toLowerCase();
    const sigLower  = (sig || "").toLowerCase();

    // ── Core signals ─────────────────────────────────────────────────
    const hasPrn       = /\bprn\b|as needed/.test(sigLower);
    const hasScheduled = /\bdaily\b|once daily|\bnightly\b|at bedtime|\bqhs\b|every\s*\d+\s*(h|hr|hour)s?\b|\bbid\b|twice daily|\btid\b|three times daily|\bqid\b|four times daily/.test(sigLower);
    const hasDuration  = /for\s+\d+\s*(day|days|week|weeks)|x\s*\d+\s*(day|days|week|weeks)|until\s+(gone|finished)|stop\s+after/.test(sigLower);
    const hasMaxDose   = /max(?:imum)?|do not exceed|\bnmt\b|no more than/.test(sigLower);
    const hasRoute     = /by mouth|orally|topically|inhale|instill|inject/.test(sigLower);
    const hasNumericDose = /\d/.test(sigLower);
    const useAsDirected  = /take as directed|use as directed|as directed/.test(sigLower);
    const highRiskPrn = hasHighRiskPrnDrug(rawText);
    const isColchicineDrug = /colchicine/i.test(String(rawText).split(/\r?\n/)[0] || "");
    const hasIntensiveSchedule = /every\s*\d+\s*(h|hr|hour)s?\b|\bbid\b|twice daily|\btid\b|three times daily|\bqid\b|four times daily/.test(sigLower);
    const hasDailySchedule = /\bdaily\b|once daily/.test(sigLower);

    // Non-negotiable HOLD boundary signals.
    const prnScheduledConflict = hasPrn && (hasIntensiveSchedule || (hasDailySchedule && (highRiskPrn || isColchicineDrug)));
    const openEndedContinuation = /until needed|continue\s+as\s+needed/.test(sigLower);

    const isAzithromycin      = /azithromycin|z-?pak|zpack/.test(textLower);
    const isPackageCourse     = /z-?pak|zpack|dosepak|dose pack|starter pack|medrol|pak/i.test(rawText || "");
    const hasTaper            = /\bthen\b|taper|decrease|reduce/.test(sigLower);
    const hasDaySequence      = /day\s*1|days?\s*2\s*[-–]\s*5|for\s*5\s*days/.test(sigLower);
    const hasCountTransition  = /2\s+tablets?.*1\s+tablet|500\s*mg.*250\s*mg/.test(textLower);
    const azithromycinQtyMismatch = isAzithromycin && Number.isFinite(qty) && qty !== 6;
    const packageWithoutStructure = isPackageCourse && !hasDaySequence && !hasCountTransition && !hasTaper;
    const qtySigConflict          = azithromycinQtyMismatch || packageWithoutStructure;

    const weeklyDosingAmbiguous = /\bweekly\b|once\s+a\s+week|1x\s*(?:per\s*)?week/.test(sigLower) &&
      !/every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)|each\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)/.test(sigLower);
    const taperWithoutSteps = hasTaper && !/\bthen\b|after\s+\d+\s+days?|reduce\s+to|day\s*\d/.test(sigLower);

    const QTY_ACUTE_THRESHOLD = 14;
    const isAcuteCourseAgent = /azithromycin|amoxicillin|levofloxacin|ciprofloxacin|doxycycline|clindamycin|metronidazole|trimethoprim|sulfamethoxazole|nitrofurantoin|cephalexin|cefdinir|augmentin|amox.clav|valacyclovir|acyclovir|famciclovir|oseltamivir|fluconazole/i.test(textLower);
    const missingHighRiskMaxDose = hasPrn && !hasMaxDose && highRiskPrn;
    const missingDurationHighImpact = isAcuteCourseAgent && hasScheduled && !hasPrn && !hasDuration &&
      Number.isFinite(qty) && qty >= QTY_ACUTE_THRESHOLD;

    // Rule 1: HOLD always overrides everything.
    if (prnScheduledConflict) return "HOLD";
    if (useAsDirected) return "HOLD"; // unclear use pattern
    if (openEndedContinuation || missingHighRiskMaxDose || missingDurationHighImpact) return "HOLD"; // exposure boundary
    if (qtySigConflict) return "HOLD";
    if (weeklyDosingAmbiguous || taperWithoutSteps) return "HOLD";

    // Rule 3 protection gate: if followable + bounded + no contradiction, do not HOLD.
    const instructionsFollowable = (hasScheduled || hasPrn) && !weeklyDosingAmbiguous && !taperWithoutSteps && !useAsDirected;
    const exposureBounded = (!hasPrn || hasMaxDose || !highRiskPrn) && (!isAcuteCourseAgent || hasDuration || !Number.isFinite(qty) || qty < QTY_ACUTE_THRESHOLD) && !openEndedContinuation;
    const noContradiction = !qtySigConflict && !prnScheduledConflict;

    // Rule 4 tie-breaker: if uncertain, decide by misuse risk.
    const couldPatientMisuseIfFollowedExactly = !instructionsFollowable || !exposureBounded || !noContradiction;
    if (couldPatientMisuseIfFollowedExactly) return "HOLD";

    // ── VERIFY: clean and self-contained ────────────────────────────
    const verifyReady =
      /^take\s+\d+(?:\.\d+)?\s+\w+/.test(sigLower) &&
      hasRoute &&
      (hasScheduled || hasPrn) &&
      hasNumericDose;

    if (verifyReady) return "VERIFY";

    // ── ADDRESS: safe but imperfect ──────────────────────────────────
    // Cleared all HOLD checks. Prescription is executable as written
    // but has at least one minor gap. Five named ADDRESS patterns:
    //   A1: nonStandardFreq  — unusual but explicitly stated frequency
    //   A2: missingRoute     — dose + schedule present; route inferrable
    //   A3: likelyStandard   — known chronic agent with interpretable sig
    //   A4: lowRiskPrnClear  — PRN with max dose stated, no conflict
    //   A5: coreSigPresent   — has dose and frequency in imperfect form
    const nonStandardFreq  = /every\s+\d+\s*(h|hr|hour)s?\b/.test(sigLower) &&
                             !/every\s+(4|6|8|12|24)\s*(h|hr|hour)s?\b/.test(sigLower);
    const weeklyWithAnchor = /twice\s+weekly|three\s+times\s+weekly|2x\s*(?:per\s*)?week|3x\s*(?:per\s*)?week/.test(sigLower);
    const missingRoute     = !hasRoute && (hasScheduled || hasPrn);
    const isChronicAgent   = /lisinopril|amlodipine|atorvastatin|rosuvastatin|simvastatin|pravastatin|metformin|metoprolol|atenolol|carvedilol|losartan|valsartan|irbesartan|olmesartan|levothyroxine|omeprazole|pantoprazole|esomeprazole|escitalopram|sertraline|fluoxetine|bupropion|venlafaxine|duloxetine|gabapentin|pregabalin/i.test(textLower);
    const likelyStandard   = isChronicAgent && hasScheduled;        // A3
    const lowRiskPrnClear  = hasPrn && hasMaxDose && !hasScheduled; // A4
    const coreSigPresent   = (hasScheduled || hasPrn) && /\d/.test(sigLower); // A5

    if (nonStandardFreq || weeklyWithAnchor || missingRoute || likelyStandard || lowRiskPrnClear || coreSigPresent) {
      return "ADDRESS"; // A1–A5: safe but imperfect
    }
    return "ADDRESS"; // fallback: cleared HOLD, did not reach VERIFY
  };

  const classifyByDecisionTree = (rawText, sig, qty) => {
    const textLower = (rawText || "").toLowerCase();
    const sigLower = (sig || "").toLowerCase();

    const GENERIC_DURATION_REVIEW_QTY_THRESHOLD = 14;
    const GENERIC_EXTENDED_COURSE_QTY_THRESHOLD = 21;

    const hasPrn = /\bprn\b|as needed/.test(sigLower);
    const hasScheduled = /\bdaily\b|once daily|\bnightly\b|at bedtime|\bqhs\b|every\s*\d+\s*(h|hr|hour)|\bbid\b|twice daily|\btid\b|three times daily|\bqid\b|four times daily/.test(sigLower);
    const hasDuration = /for\s+\d+\s*(day|days|week|weeks)|x\s*\d+\s*(day|days|week|weeks)|until\s+(gone|finished)|stop\s+after/.test(sigLower);
    const hasMaxDose = /max(?:imum)?|do not exceed|nmt\b|no more than/.test(sigLower);
    const highRiskPrn = hasHighRiskPrnDrug(rawText);
    const unclearUsePattern = /take as directed|use as directed|as directed/.test(sigLower);
    const conflictingFrequency = /\bdaily\b/.test(sigLower) && /every\s*\d+\s*(h|hr|hour)/.test(sigLower);
    const unclearStopPoint = /until needed|continue\s+as\s+needed/.test(sigLower);

    const genericMissingDurationReview =
      hasScheduled && !hasPrn && Number.isFinite(qty) && qty >= GENERIC_DURATION_REVIEW_QTY_THRESHOLD && !hasDuration;
    const genericExtendedCourseWithoutStop =
      hasScheduled && Number.isFinite(qty) && qty >= GENERIC_EXTENDED_COURSE_QTY_THRESHOLD && !hasDuration;
    const missingHighRiskMaxDose = hasPrn && !hasMaxDose && highRiskPrn;
    const hasNightlySchedule = /\bnightly\b|at bedtime|\bqhs\b/.test(sigLower);
    const hasStopPointSignal = /until\s+(gone|finished|resolved)|stop\s+after|discontinue\s+after/.test(sigLower);
    const repeatIntervalMatch = sigLower.match(/every\s*(\d+)\s*(h|hr|hour)s?\b/);
    const repeatIntervalHours = repeatIntervalMatch ? Number(repeatIntervalMatch[1]) : null;
    const hasNonStandardRepeatInterval = repeatIntervalHours !== null && ![4, 6, 8, 12, 24].includes(repeatIntervalHours);

    const getAddressReason = () => {
      if (hasPrn && !hasMaxDose) {
        return {
          structural: "PRN directions do not state a maximum dose or daily-use limit.",
          refresh: [
            "Step 3 ADDRESS triggered: PRN wording is usable, but a maximum-use boundary is not stated.",
            "Pattern focus: this is a structured max-dose clarification request, not a contradiction.",
            "Next step: clarify max dose during workflow."
          ],
          message: "Clarify max dose: PRN directions are missing a maximum-use boundary.",
        };
      }

      if (hasNonStandardRepeatInterval) {
        return {
          structural: "Repeat interval is present but should be confirmed for a clear administration cadence.",
          refresh: [
            "Step 3 ADDRESS triggered: repeat interval wording is present but not on a standard cadence pattern.",
            "Pattern focus: confirm repeat interval so administration timing is explicit.",
            "Next step: clarify repeat interval during workflow."
          ],
          message: "Clarify repeat interval: confirm administration timing pattern.",
        };
      }

      if (hasPrn && !/as needed for|prn for/.test(sigLower)) {
        return {
          structural: "As-needed directions are present, but use-pattern trigger wording is not explicit.",
          refresh: [
            "Step 3 ADDRESS triggered: PRN structure is interpretable, but trigger wording is not explicit.",
            "Pattern focus: clarify use pattern so episodic use trigger is clear.",
            "Next step: clarify use pattern during workflow."
          ],
          message: "Clarify use pattern: PRN trigger wording should be explicit.",
        };
      }

      if ((hasScheduled || hasNightlySchedule) && !hasDuration && /azithromycin|amoxicillin|levofloxacin|ciprofloxacin|doxycycline|clindamycin|metronidazole|trimethoprim|sulfamethoxazole|nitrofurantoin|cephalexin|cefdinir|augmentin|amox.clav|valacyclovir|acyclovir|famciclovir|oseltamivir|fluconazole/i.test(textLower)) {
        return {
          structural: "Course duration is not explicit for a course-structured regimen.",
          refresh: [
            "Step 3 ADDRESS triggered: schedule is readable, but course endpoint is not explicit.",
            "Pattern focus: confirm course length for complete duration structure.",
            "Next step: confirm course length during workflow."
          ],
          message: "Confirm course length: duration wording should be explicit.",
        };
      }

      if ((hasScheduled || hasNightlySchedule) && !hasStopPointSignal && /until|continue/.test(sigLower)) {
        return {
          structural: "Stop-point wording should be clarified so endpoint boundaries are explicit.",
          refresh: [
            "Step 3 ADDRESS triggered: ongoing wording is present, but explicit stop-point wording is incomplete.",
            "Pattern focus: clarify stop point so continuation endpoint is explicit.",
            "Next step: clarify stop point during workflow."
          ],
          message: "Clarify stop point: endpoint wording should be explicit.",
        };
      }

      if (!hasScheduled && !hasNightlySchedule && !hasPrn) {
        return {
          structural: "Schedule wording should be confirmed so administration timing is explicit.",
          refresh: [
            "Step 3 ADDRESS triggered: dose wording is present, but schedule wording is not explicit.",
            "Pattern focus: confirm schedule to complete administration timing structure.",
            "Next step: confirm schedule during workflow."
          ],
          message: "Confirm schedule: administration timing should be explicit.",
        };
      }

      return null;
    };

    const challengeResolution = { label: "CHALLENGE", emoji: "🔴", bg: "bg-red-50", border: "border-red-300", text: "text-red-900" };
    const addressResolution = { label: "CLARIFY USE", emoji: "🟠", bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-900" };
    const verifyResolution = { label: "NONE", emoji: "🟢", bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-900" };

    const assessPatternSpecificRegimen = () => {
      const isPackageCourse = /z-?pak|zpack|dosepak|dose pack|starter pack|medrol|pak/i.test(rawText || "");
      const isAzithromycinPackage = /azithromycin|z-?pak|zpack/.test(textLower);
      const hasTaperStructure = /\bthen\b|taper|decrease|reduce/.test(sigLower);
      const hasExplicitDaySequence = /day\s*1|days?\s*2\s*[-–]\s*5|for\s*5\s*days/.test(sigLower);
      const hasTabletCountTransition = /2\s+tablets?.*1\s+tablet|500\s*mg.*250\s*mg/.test(textLower);
      const azithromycinPackageQtyMismatch = isAzithromycinPackage && Number.isFinite(qty) && qty !== 6;
      const azithromycinPackagePatternMismatch = isAzithromycinPackage && !hasExplicitDaySequence && !hasTabletCountTransition;
      const taperWithoutTransition = hasTaperStructure && !/\bthen\b|after\s+\d+\s+days?|reduce\s+to/.test(sigLower);
      const packagePatternMismatch = isPackageCourse && !hasExplicitDaySequence && !hasTabletCountTransition && !hasTaperStructure;

      if (azithromycinPackageQtyMismatch || azithromycinPackagePatternMismatch) {
        return {
          lane: "CHALLENGE",
          structural: "Written regimen does not match a recognizable azithromycin package-style pattern.",
          affects: "instructions",
          clarification: "Likely",
          resolution: challengeResolution,
          refresh: [
            "Pattern-specific check triggered: azithromycin package-course structure is not internally recognizable.",
            "Pattern focus: package-based regimen math and day-sequencing should align to a coherent written structure.",
            "Next step: clarify the written regimen structure before dispensing."
          ],
          message: "Regimen structure does not match a recognizable azithromycin package-style course. Please clarify the written instructions.",
        };
      }

      if (taperWithoutTransition || packagePatternMismatch) {
        return {
          lane: "CHALLENGE",
          structural: "Structured regimen pattern is incomplete or does not resolve into a clear package/taper sequence.",
          affects: "instructions",
          clarification: "Likely",
          resolution: challengeResolution,
          refresh: [
            "Pattern-specific check triggered: package/taper sequence is not structurally complete.",
            "Pattern focus: structured regimens should show a recognizable sequence and quantity relationship.",
            "Next step: clarify the regimen sequence before dispensing."
          ],
          message: "Structured regimen sequence is incomplete or mismatched. Please clarify the written course before dispensing.",
        };
      }

      return null;
    };

    const verifyReady =
      /^take\s+\d+(?:\.\d+)?\s+\w+/.test(sigLower) &&
      /by mouth|orally|topically|inhale|instill|inject/.test(sigLower) &&
      (hasScheduled || hasPrn) &&
      !unclearUsePattern;

    const preclassifiedLane = preclassifyLane(rawText, sig, qty);

    if (preclassifiedLane === "HOLD" && ((hasPrn && hasScheduled) || conflictingFrequency || unclearUsePattern)) {
      return {
        lane: "CHALLENGE",
        structural: "SIG structure mixes scheduled and as-needed use or competing timing paths, so one clear use path is not stated.",
        affects: "instructions",
        clarification: "Likely",
        resolution: challengeResolution,
        refresh: [
          "Step 1 followability triggered: the SIG mixes scheduled and as-needed use or combines timing patterns that create competing use paths.",
          "Pattern focus: it is unclear whether the order is intended for ongoing daily use or intermittent episodic use, so one clear use path is not stated.",
          "Next step: request one clear use path before dispensing."
        ],
        message: "SIG structure is unclear because scheduled and as-needed use are mixed without one clear use path. Please clarify intended use structure before dispensing.",
      };
    }

    if (preclassifiedLane === "HOLD") {
      const patternSpecificRegimenIssue = assessPatternSpecificRegimen();
      if (patternSpecificRegimenIssue) return patternSpecificRegimenIssue;
    }

    if (preclassifiedLane === "HOLD" && (genericMissingDurationReview || missingHighRiskMaxDose || genericExtendedCourseWithoutStop || unclearStopPoint)) {
      return {
        lane: "CHALLENGE",
        structural: "SIG does not clearly state duration, stop-point, or maximum-use boundary.",
        affects: "duration",
        clarification: "Likely",
        resolution: challengeResolution,
        refresh: [
          "Step 2 exposure-clarity triggered: duration, stop-point, or maximum-use wording is incomplete in the SIG.",
          "Pattern focus: without an explicit endpoint or limit, total exposure cannot be read directly from the written directions.",
          "Next step: request explicit duration, stop-point, or maximum-use wording before dispensing."
        ],
        message: "Exposure boundary is unclear because duration, stop-point, or maximum-use wording is missing. Please clarify before dispensing.",
      };
    }

    if (preclassifiedLane === "VERIFY") {
      return {
        lane: "VERIFY AS ENTERED",
        structural: "No obvious structural issue detected.",
        affects: "none",
        clarification: "Unlikely",
        resolution: verifyResolution,
        refresh: [
          "Step 4 clear: directions are interpretable and structurally complete.",
          "Pattern focus: no blocking ambiguity found.",
          "Next step: verify as entered."
        ],
        message: "No message needed.",
      };
    }

    if (preclassifiedLane === "ADDRESS") {
      const addressReason = getAddressReason();
      if (!addressReason) {
        return {
          lane: "VERIFY AS ENTERED",
          structural: "No obvious structural issue detected.",
          affects: "none",
          clarification: "Unlikely",
          resolution: verifyResolution,
          refresh: [
            "Step 4 clear: directions are interpretable and structurally complete.",
            "Pattern focus: no specific structural clarification reason remained after ADDRESS screening.",
            "Next step: verify as entered."
          ],
          message: "No message needed.",
        };
      }
      return {
        lane: "CLARIFY USE",
        structural: addressReason.structural,
        affects: "instructions",
        clarification: "Likely",
        resolution: addressResolution,
        refresh: addressReason.refresh,
        message: addressReason.message,
      };
    }

    const fallbackAddressReason = getAddressReason();
    if (!fallbackAddressReason) {
      return {
        lane: "VERIFY AS ENTERED",
        structural: "No obvious structural issue detected.",
        affects: "none",
        clarification: "Unlikely",
        resolution: verifyResolution,
        refresh: [
          "Step 4 clear: directions are interpretable and structurally complete.",
          "Pattern focus: no specific structural clarification reason remained after fallback ADDRESS screening.",
          "Next step: verify as entered."
        ],
        message: "No message needed.",
      };
    }

    return {
      lane: "CLARIFY USE",
      structural: fallbackAddressReason.structural,
      affects: "instructions",
      clarification: "Likely",
      resolution: addressResolution,
      refresh: fallbackAddressReason.refresh,
      message: fallbackAddressReason.message,
    };
  };

  const buildCaseFromInput = (rawText) => {
    const originalText = String(rawText || "").trim();
    if (!originalText) return null;

    const correctionNotes = [];
    const squashed = originalText.replace(/\s+/g, " ").trim();
    if (squashed !== originalText) correctionNotes.push("Collapsed extra spacing.");

    let normalizedText = squashed.replace(/qty\s*([0-9]+)/gi, "qty $1");
    if (normalizedText !== squashed) correctionNotes.push("Normalized quantity token spacing (e.g., qty30 -> qty 30).");

    const qtyMatch = normalizedText.match(/\b(?:qty|quantity)\b\s*[:\-]?\s*([0-9]{1,3})\b/i) || normalizedText.match(/\(\s*qty\s*([0-9]{1,3})\s*\)/i);
    if (!qtyMatch) {
      return {
        input_status: "INVALID",
        input_error: "Could not reliably identify quantity.",
        expected_structure: "Drug - SIG (qty number)",
      };
    }

    const qty = Number(qtyMatch[1]);
    normalizedText = normalizedText.replace(/\(\s*qty\s*[:\-]?\s*[0-9]{1,3}\s*\)/ig, "");
    normalizedText = normalizedText.replace(/\b(?:qty|quantity)\b\s*[:\-]?\s*[0-9]{1,3}\b/ig, "").replace(/\s+/g, " ").trim();

    const parts = normalizedText.split(/\s+-\s+/);
    let rawDrugChunk = parts[0] || "";
    let rawSigChunk = parts.slice(1).join(" - ");

    if (!rawSigChunk) {
      const inlineSigMatch = normalizedText.match(/\b(take|use|apply|inhale|instill|inject)\b/i);
      if (inlineSigMatch) {
        rawDrugChunk = normalizedText.slice(0, inlineSigMatch.index).trim();
        rawSigChunk = normalizedText.slice(inlineSigMatch.index).trim();
      }
    }

    const normalizedDrug = normalizeDrugChunk(rawDrugChunk);
    if (!normalizedDrug.ok) {
      return {
        input_status: "INVALID",
        input_error: normalizedDrug.error,
        expected_structure: "Drug: <name + strength>",
      };
    }
    correctionNotes.push(...normalizedDrug.correctionNotes);

    const normalizedSig = normalizeSigText(rawSigChunk);
    if (!normalizedSig || !/\b(take|use|apply|inhale|instill|inject)\b/.test(normalizedSig)) {
      return {
        input_status: "INVALID",
        input_error: "Could not reliably identify SIG directions.",
        expected_structure: "SIG: <directions>",
      };
    }

    if (normalizedSig !== rawSigChunk.toLowerCase().replace(/\s+/g, " ").trim()) {
      correctionNotes.push("Normalized SIG shorthand/typos (e.g., po, qhs, bid, prn, daliy, nigtly).");
    }

    const normalizedInput = `${normalizedDrug.value} - ${normalizedSig} (qty ${qty})`;
    const text = normalizedInput;

    const strengthMatch = normalizedDrug.value.match(/\b([0-9]+(?:\.[0-9]+)?)\s*(mg|gm|g|mcg)\b/i);
    const strength = strengthMatch ? `${strengthMatch[1]} ${strengthMatch[2].toLowerCase()}` : "";

    const titleWithoutQty = normalizedDrug.value.trim();

    const titleHasStrength = strength
      ? (() => {
          const match = strength.match(/^([0-9]+(?:\.[0-9]+)?)\s*(mg|gm|g|mcg)$/i);
          if (!match) return false;
          const numericPart = match[1];
          const unitPart = match[2];
          const flexibleStrengthPattern = new RegExp(`\\b${numericPart}\\s*${unitPart}\\b`, "i");
          return flexibleStrengthPattern.test(titleWithoutQty);
        })()
      : false;

    const title = strength && !titleHasStrength
      ? `${titleWithoutQty} ${strength}`.trim()
      : titleWithoutQty;

    const sig = normalizedSig;

    const classification = classifyByDecisionTree(text, sig, qty);

    return {
      title,
      sig,
      qty,
      input_status: correctionNotes.length ? "NORMALIZED" : "CLEAN",
      normalized_input: correctionNotes.length ? normalizedInput : null,
      correction_notes: correctionNotes,
      ...classification,
    };
  };

  const buildInterpretedAsText = (nextCase) => {
    if (!nextCase) return "";

    const displayDrug = String(nextCase.title || "")
      .toLowerCase()
      .replace(/\b([0-9]+(?:\.[0-9]+)?)\s*gm\b/g, "$1 g")
      .replace(/\b([0-9]+(?:\.[0-9]+)?)\s*ug\b/g, "$1 mcg")
      .replace(/\b([0-9]+(?:\.[0-9]+)?)\s*(mg|mcg|g)\b/g, "$1 $2")
      .replace(/\s+/g, " ")
      .trim()
      .split(" ")
      .map((token) => {
        if (/^[0-9]+(?:\.[0-9]+)?$/.test(token)) return token;
        if (/^(mg|mcg|g)$/.test(token)) return token;
        return token.charAt(0).toUpperCase() + token.slice(1);
      })
      .join(" ");

    const sig = String(nextCase.sig || "").toLowerCase();
    const sigTokens = [];

    if (/\b(four times daily|qid|every\s*6\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("QID");
    else if (/\b(three times daily|tid|every\s*8\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("TID");
    else if (/\b(twice daily|bid|every\s*12\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("BID");
    else if (/\b(nightly|at bedtime|qhs)\b/.test(sig)) sigTokens.push("QHS");
    else if (/\b(once daily|daily|qd|every\s*24\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("QD");

    if (/\b(as needed|prn)\b/.test(sig)) sigTokens.push("PRN");
    if (sigTokens.length === 0) sigTokens.push("Freq Unspecified");

    const parts = [displayDrug, ...sigTokens, `Qty ${nextCase.qty}`].filter(Boolean);
    return parts.join(" | ");
  };

  const handleAnalyze = () => {
    const nextCase = buildCaseFromInput(prescriptionInput);
    if (!nextCase) return;

    if (nextCase.input_status === "INVALID") {
      setInputFeedback({
        type: "invalid",
        message: `${nextCase.input_error} Expected: ${nextCase.expected_structure || "Drug - SIG (qty number)"}`,
      });
      setInterpretedAsText("");
      return;
    }

    if (nextCase.input_status === "NORMALIZED") {
      setInputFeedback({
        type: "normalized",
        message: `Normalized input: ${nextCase.normalized_input}`,
      });
    } else {
      setInputFeedback({ type: "clean", message: "Input accepted as entered." });
    }

    setInterpretedAsText(buildInterpretedAsText(nextCase));

    addCaseAndSelect(nextCase, sourceRefInput);
    setPrescriptionInput("");
    setSourceRefInput("");
  };

  const lanePriority = {
    "HOLD NOW": 1,
    "ADDRESS DURING WORKFLOW": 2,
    "PENDING": 3,
    "VERIFY": 4,
    "RESOLVED": 5,
  };

  const confidencePriority = {
    HIGH: 3,
    MEDIUM: 2,
    LOW: 1,
    null: 0,
  };

  const sortQueueItems = (entries, sectionTitle) => {
    return [...entries].sort((a, b) => {
      if (sectionTitle === "PENDING") {
        const aMovedAt = pendingMovedAtById[a.item.id] || 0;
        const bMovedAt = pendingMovedAtById[b.item.id] || 0;
        if (bMovedAt !== aMovedAt) return bMovedAt - aMovedAt;
      }

      const aConfidence = getConfidenceMeta(a.item, a.status)?.level || null;
      const bConfidence = getConfidenceMeta(b.item, b.status)?.level || null;
      const aRank = confidencePriority[aConfidence] ?? 0;
      const bRank = confidencePriority[bConfidence] ?? 0;
      if (bRank !== aRank) return bRank - aRank;

      return a.idx - b.idx;
    });
  };

  const queueGroups = [
    {
      title: "HOLD NOW",
      tone: "red",
      items: cases
        .map((item, idx) => ({ item, idx, status: caseStatuses[item.id] || "active" }))
        .filter((entry) => entry.status === "active" && entry.item.lane === "CHALLENGE"),
      accent: "border-red-200 bg-red-50/40",
    },
    {
      title: "ADDRESS DURING WORKFLOW",
      tone: "amber",
      items: cases
        .map((item, idx) => ({ item, idx, status: caseStatuses[item.id] || "active" }))
        .filter((entry) => entry.status === "active" && ["CLARIFY USE", "COMPLETE"].includes(entry.item.lane)),
      accent: "border-amber-200 bg-amber-50/40",
    },
    {
      title: "VERIFY",
      tone: "green",
      items: cases
        .map((item, idx) => ({ item, idx, status: caseStatuses[item.id] || "active" }))
        .filter((entry) => entry.status === "active" && ["VERIFY AS ENTERED", "NONE"].includes(entry.item.lane)),
      accent: "border-emerald-200 bg-emerald-50/30",
    },
    {
      title: "PENDING",
      tone: "yellow",
      items: cases
        .map((item, idx) => ({ item, idx, status: caseStatuses[item.id] || "active" }))
        .filter((entry) => entry.status === "pending"),
      accent: "border-yellow-200 bg-yellow-50/40",
    },
    {
      title: "RESOLVED",
      tone: "green",
      items: cases
        .map((item, idx) => ({ item, idx, status: caseStatuses[item.id] || "active" }))
        .filter((entry) => entry.status === "resolved"),
      accent: "border-emerald-200 bg-emerald-50/30",
    },
  ]
    .sort((a, b) => (lanePriority[a.title] || 99) - (lanePriority[b.title] || 99))
    .map((group) => ({
      ...group,
      items: sortQueueItems(group.items, group.title),
    }));

  const [copiedById, setCopiedById] = React.useState({});
  const [pendingButtonById, setPendingButtonById] = React.useState({});
  const [pendingSavingById, setPendingSavingById] = React.useState({});
  const [resolvedButtonById, setResolvedButtonById] = React.useState({});

  const copyMessage = async () => {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(active.message);
    const caseId = active?.id;
    if (!caseId) return;
    setCopiedById((prev) => ({ ...prev, [caseId]: true }));
    setTimeout(() => {
      setCopiedById((prev) => ({ ...prev, [caseId]: false }));
    }, 1500);
  };

  const markAsPending = async () => {
    const caseId = active?.id;
    if (!caseId) return;
    if (pendingSavingById[caseId]) return;
    setPendingSavingById((prev) => ({ ...prev, [caseId]: true }));

    const pendingOriginMeta = getPendingOriginMeta(active);
    try {
      await new Promise((resolve) => setTimeout(resolve, 350));
      setCaseStatuses((prev) => ({ ...prev, [caseId]: "pending" }));
      setPendingSubStatus((prev) => ({
        ...prev,
        [caseId]: pendingOriginMeta?.subStatus || "Awaiting clarification",
      }));
      setPendingOriginById((prev) => ({
        ...prev,
        [caseId]: pendingOriginMeta,
      }));
      setPendingMovedAtById((prev) => ({ ...prev, [caseId]: Date.now() }));
      setPendingButtonById((prev) => ({ ...prev, [caseId]: true }));
      setActiveCaseId(caseId);
    } finally {
      setPendingSavingById((prev) => ({ ...prev, [caseId]: false }));
    }
  };

  const markResolved = () => {
    const caseId = active?.id;
    if (!caseId) return;
    setCaseStatuses((prev) => ({ ...prev, [caseId]: "resolved" }));
    setResolvedButtonById((prev) => ({ ...prev, [caseId]: true }));
    setActiveCaseId(caseId);
  };

  const formatSeenBeforeTimestamp = (isoValue) => {
    if (!isoValue) return "Not available";
    const d = new Date(isoValue);
    if (Number.isNaN(d.getTime())) return "Not available";
    return d.toLocaleString();
  };

  return (
    <div className="min-h-screen bg-slate-100 p-4 font-sans text-slate-900 md:p-6">
      <div className="mx-auto grid max-w-7xl gap-4 lg:h-[calc(100vh-3rem)] lg:grid-cols-[360px_1fr] lg:gap-6">
        <aside className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm lg:overflow-auto">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Pharmacy101</div>
              <h1 className="text-xl font-semibold">Decision Queue Demo</h1>
            </div>
            <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">Live Check</div>
          </div>

          <div className="mb-3 rounded-2xl border border-slate-200 bg-white p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Quick Actions</div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => loadQuickAction("missing-max-dose")}
                className="rounded-lg border border-yellow-200 bg-yellow-50 px-2.5 py-1 text-xs font-semibold text-yellow-900 hover:bg-yellow-100"
              >
                Missing Max Dose
              </button>
              <button
                type="button"
                onClick={() => loadQuickAction("prn-use-unclear")}
                className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-100"
              >
                PRN Use Unclear
              </button>
              <button
                type="button"
                onClick={() => loadQuickAction("duration-quantity-mismatch")}
                className="rounded-lg border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-900 hover:bg-red-100"
              >
                Duration Quantity Mismatch
              </button>
              <button
                type="button"
                onClick={() => loadQuickAction("scheduled-vs-prn-conflict")}
                className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-100"
              >
                Scheduled vs PRN Conflict
              </button>
              <button
                type="button"
                onClick={() => loadQuickAction("extended-duration-mismatch")}
                className="rounded-lg border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-900 hover:bg-red-100"
              >
                Extended Duration Mismatch
              </button>
            </div>
            <div className="mt-3">
              <button
                type="button"
                onClick={handleExportAuditLog}
                disabled={isExportingAudit || auditCount <= 0}
                className={`w-full rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${
                  isExportingAudit || auditCount <= 0
                    ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
                    : "border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100"
                }`}
              >
                {isExportingAudit ? "Exporting..." : "Export Audit Log"}
              </button>
              {auditCount <= 0 && (
                <div className="mt-1 text-[11px] text-slate-500">No analyses available to export yet.</div>
              )}
            </div>
          </div>

          <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-3">
            <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-600">
              Enter prescription
            </label>
            <textarea
              value={prescriptionInput}
              onChange={(event) => setPrescriptionInput(event.target.value)}
              placeholder="Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)"
              rows={3}
              className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            />
            <div className="mt-1 text-[11px] text-slate-500">Accepted examples: "Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)" or "valacyclovir 1 g take 1 tab q12h qty 28".</div>
            <div className="mt-1 text-[11px] text-slate-500">Hyphen is optional. Quantity may be qty 28, quantity 28, or (qty 28). Extra spaces are okay.</div>
            <input
              type="text"
              value={sourceRefInput}
              onChange={(event) => setSourceRefInput(event.target.value)}
              placeholder="Source Ref (e.g., eRx 284193, Order 771245) — optional"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            />
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={handleAnalyze}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
              >
                Analyze
              </button>
            </div>
            {inputFeedback && (
              <div className={`mt-2 rounded-lg border px-2 py-1 text-xs ${
                inputFeedback.type === "invalid"
                  ? "border-red-200 bg-red-50 text-red-700"
                  : inputFeedback.type === "normalized"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }`}>
                {inputFeedback.message}
              </div>
            )}
            {interpretedAsText && (
              <div className="mt-2 text-xs text-slate-600">
                <span className="font-semibold text-slate-700">Interpreted as:</span> {interpretedAsText}
              </div>
            )}
          </div>

          <div className="space-y-4">
            {queueGroups.map((group) => (
              <section key={group.title} className={`rounded-2xl border p-3 ${group.accent}`}>
                <h2 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-700">
                  <span className={`inline-block h-2 w-2 rounded-full ${getToneDotClass(group.tone)}`} />
                  {group.title}
                </h2>

                <div className="space-y-2">
                  {group.items.length === 0 && (
                    <div className="rounded-xl bg-white/70 p-3 text-xs text-slate-500">No Items</div>
                  )}

                  {group.items.map(({ item, idx, status }) => {
                    const isActive = item.id === active?.id;
                    const statusLine = status === "pending" ? `PENDING → ${getShortActionPhrase(item, status, item.id)}` : `${group.title} → ${getShortActionPhrase(item, status, item.id)}`;
                    const itemSourceRef = sourceRefById[item.id];
                    const confidence = getConfidenceMeta(item, status);
                    return (
                      <button
                        type="button"
                        key={`${item.title}-${idx}`}
                        onClick={() => setActiveCaseId(item.id)}
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          isActive
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className={`text-xs font-semibold ${isActive ? "text-slate-200" : "text-slate-600"}`}>
                            {statusLine}
                          </div>
                          {confidence && (
                            <div
                              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] ${isActive ? "border-slate-600 bg-slate-800 text-slate-200 font-semibold" : confidence.className}`}
                              style={!isActive ? confidence.style : undefined}
                            >
                              {confidence.level}
                            </div>
                          )}
                        </div>
                        <div className="mt-1 text-sm font-semibold">{getQueueDrugName(item)}</div>
                        <div className={`mt-1 line-clamp-1 text-xs ${isActive ? "text-slate-300" : "text-slate-500"}`}>
                          {item.sig}
                        </div>
                        <div className={`mt-1 text-xs ${isActive ? "text-slate-300" : "text-slate-500"}`}>Qty {item.qty}</div>
                        {itemSourceRef && (
                          <div className={`mt-1 text-xs font-medium ${isActive ? "text-slate-300" : "text-slate-600"}`}>
                            Source Ref: {itemSourceRef}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </aside>

        <main className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm lg:flex lg:min-h-0 lg:flex-col lg:overflow-y-auto">
          <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            {(() => {
              const visibleHeader = getVisibleHeaderState(active, activeStatus);
              return (
            <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
              <div className={`inline-flex rounded-xl border px-4 py-2 text-base font-bold ${visibleHeader.bg} ${visibleHeader.border} ${visibleHeader.text}`}>
                <span className="inline-flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${getToneDotClass(visibleHeader.tone)}`} />
                  {visibleHeader.label}
                </span>
              </div>
              <div className={`text-base font-bold uppercase tracking-wide ${visibleHeader.text}`}>
                → {getShortActionPhrase(active, activeStatus, active?.id)}
              </div>
            </div>
              );
            })()}

            <div className="mb-1 text-2xl font-semibold leading-tight">{active.title}</div>
            {sourceRefById[active?.id] && (
              <div className="mb-3 text-xs font-medium text-slate-500">Source Ref: {sourceRefById[active?.id]}</div>
            )}
            {active?.input_status === "NORMALIZED" && active?.normalized_input && (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                <div className="font-semibold">Normalized Input</div>
                <div>{active.normalized_input}</div>
                {Array.isArray(active.correction_notes) && active.correction_notes.length > 0 && (
                  <div className="mt-1">Notes: {active.correction_notes.join(" | ")}</div>
                )}
              </div>
            )}

            <div className="mb-3 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
              <div className="font-semibold uppercase tracking-[0.08em] text-slate-500">Seen Before</div>
              {(() => {
                const knownPattern = String(active?.known_pattern_message || "").trim();
                const priorRxDisplay = String(active?.seen_before_context?.display || "").trim();

                if (knownPattern) {
                  return <div className="mt-1 text-sm font-semibold text-slate-800">Previously clarified on this prescription</div>;
                }
                if (priorRxDisplay) {
                  return <div className="mt-1 text-sm font-semibold text-slate-800">{priorRxDisplay}</div>;
                }
                return <div className="mt-1 text-sm font-semibold text-slate-800">No prior history</div>;
              })()}
            </div>

            <div className="grid gap-2 text-sm sm:grid-cols-[1fr_auto]">
              <div className="rounded-xl bg-white p-3 text-slate-700">{active.sig}</div>
              <div className="rounded-xl bg-white p-3 font-semibold text-slate-700">Qty {active.qty}</div>
            </div>

            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Decision</div>
              <div className="mt-1 text-sm font-semibold text-slate-900">
                {getPrimaryActionInstruction(active, activeStatus, active?.id)}
              </div>
              <div className="mt-1 text-sm text-slate-600">{getSupportingContextLine(active)}</div>
            </div>

            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Quick Rationale</div>
              {(() => {
                const rationale = getQuickRationale(active);
                return (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    <li><span className="font-semibold text-slate-900">Typical:</span> {rationale.typical}</li>
                    <li><span className="font-semibold text-slate-900">Deviation:</span> {rationale.deviation}</li>
                    <li><span className="font-semibold text-slate-900">Risk:</span> {rationale.risk}</li>
                  </ul>
                );
              })()}
            </div>
          </section>

          <section className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={markResolved}
                className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-slate-700 active:bg-slate-800 transition-colors"
              >
                {resolvedButtonById[active?.id]
                  ? "Resolved"
                  : "Mark Resolved"}
              </button>
              <button
                type="button"
                onClick={copyMessage}
                className="rounded-xl border border-slate-300 bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                {copiedById[active?.id]
                  ? "Copied"
                  : "Copy Message"}
              </button>
              <button
                type="button"
                onClick={markAsPending}
                disabled={Boolean(pendingSavingById[active?.id])}
                className="rounded-xl border border-amber-300 bg-amber-50 px-5 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {pendingSavingById[active?.id]
                  ? "Saving..."
                  : pendingButtonById[active?.id]
                    ? "Pending"
                    : "Send to Pending"}
              </button>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700">{getPrimaryActionInstruction(active, activeStatus, active?.id)}</div>

            <textarea
              value={notesById[active?.id] || ""}
              onChange={(event) =>
                setNotesById((prev) => ({
                  ...prev,
                  [active?.id]: event.target.value,
                }))
              }
              placeholder="Add note (optional)"
              rows={2}
              className="mt-3 w-full resize-none rounded-xl border border-slate-200 bg-white p-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            />
          </section>

          <details className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <summary className="cursor-pointer text-xs font-medium text-slate-500">Expanded Detail</summary>
            <div className="mt-3 space-y-2">
              {(() => {
                const confidence = getConfidenceMeta(active, activeStatus);
                if (!confidence) return null;
                return (
                  <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                    Confidence: <span className="font-semibold">{confidence.level}</span>
                  </div>
                );
              })()}
              <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                {getDebugLaneSummary(active, activeStatus)}
              </div>
              {active.refresh.map((line, idx) => (
                <div key={idx} className="rounded-xl bg-slate-50 p-3 text-sm leading-6 text-slate-600">
                  {line}
                </div>
              ))}
              {active?.message && active.message !== "No message needed." && (
                <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                  Full message: {active.message}
                </div>
              )}
              <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                Affects: <span className="font-semibold capitalize">{active.affects}</span>
              </div>
            </div>
          </details>
        </main>
      </div>
    </div>
  );
}
