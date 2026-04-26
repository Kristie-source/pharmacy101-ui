(() => {
  console.log("PHARMACY EXTENSION LIVE");
  if (window.__pharmacy101FloatingPanelLoaded) return;
  window.__pharmacy101FloatingPanelLoaded = true;

  const host = document.createElement("div");
  host.id = "p101-host";
  document.documentElement.appendChild(host);

  const shadowRoot = host.attachShadow({ mode: "open" });

  const styleLink = document.createElement("link");
  styleLink.rel = "stylesheet";
  styleLink.href = chrome.runtime.getURL("panel.css");
  shadowRoot.appendChild(styleLink);

  const launcher = document.createElement("button");
  launcher.id = "p101-launcher";
  launcher.type = "button";
  launcher.textContent = "Pharmacy101";

  const panelWrap = document.createElement("div");
  panelWrap.id = "p101-panel-wrap";
  panelWrap.innerHTML = `
    <section id="p101-panel" aria-label="Pharmacy101 panel">
      <header id="p101-panel-header">
        <div class="p101-title-wrap">
          <div class="p101-kicker">Pharmacy101</div>
          <div class="p101-title">Floating Analysis Panel</div>
        </div>
        <button id="p101-close" type="button">Close</button>
      </header>
      <div id="p101-body">
        <div class="p101-card">
          <label class="p101-label" for="p101-input">Enter prescription</label>
          <textarea id="p101-input" placeholder="Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)"></textarea>
          <div class="p101-helper">Examples: "Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)" or "valacyclovir 1 g take 1 tab q12h qty 28".</div>
          <div class="p101-helper">Hyphen optional. Quantity supports qty 28, quantity 28, or (qty 28).</div>
          <input id="p101-source" type="text" placeholder="Source Ref (optional)" />
          <div class="p101-actions"><button id="p101-analyze" type="button">Analyze</button></div>
          <div id="p101-feedback"></div>
          <div id="p101-interpreted"></div>
        </div>

        <div id="p101-result">
          <div id="p101-action-badge" class="p101-action-badge"></div>
          <div id="p101-action-summary" class="p101-action-summary"></div>
          <div id="p101-issue-line" class="p101-issue-line"></div>
          <div id="p101-why-this-matters" class="p101-why-line"></div>
          <div id="p101-action-line" class="p101-action-line"></div>
          <div id="p101-known-pattern" class="p101-known-pattern" style="display:none;"></div>
          <div id="p101-seen-before" class="p101-seen-before" style="display:none;"></div>

          <details id="p101-secondary" class="p101-secondary">
            <summary>Supporting details</summary>
            <div id="p101-confidence-tag" class="p101-secondary-line" style="display:none;"></div>
            <div id="p101-documentation" class="p101-secondary-line"></div>
            <div id="p101-internal-message" class="p101-secondary-line"></div>
            <div id="p101-refresh-points" class="p101-secondary-line"></div>
            <div id="p101-structural-issue" class="p101-secondary-line"></div>
            <div id="p101-history-summary" class="p101-secondary-line"></div>
          </details>

          <div class="p101-resolve-row">
            <button id="p101-mark-resolved" type="button">Mark as Resolved</button>
            <button id="p101-copy" type="button">Copy Message</button>
            <button id="p101-mark-pending" type="button">Send to Pending</button>
          </div>

          <div id="p101-resolve-panel" class="p101-resolve-panel" style="display:none;">
            <div class="p101-resolve-title">How was this resolved?</div>
            <label class="p101-mini-label" for="p101-resolve-state">Resolution</label>
            <select id="p101-resolve-state">
              <option value="intent_confirmed_sig_unchanged">Confirmed with MD</option>
              <option value="intentional_nonstandard">Intentional / off-label</option>
              <option value="structure_fixed">Structure fixed</option>
              <option value="accepted_as_is">Accept as-is</option>
            </select>

            <label class="p101-mini-label" for="p101-resolve-note">Note</label>
            <textarea id="p101-resolve-note" rows="2" placeholder="Optional unless Accept as-is"></textarea>

            <label class="p101-mini-label" for="p101-resolve-scope">Suppression scope</label>
            <select id="p101-resolve-scope">
              <option value="PATIENT_ONLY" selected>PATIENT_ONLY</option>
              <option value="PATIENT_PRESCRIBER">PATIENT_PRESCRIBER</option>
            </select>

            <label class="p101-mini-label" for="p101-resolve-pharmacist-id">Pharmacist ID</label>
            <input id="p101-resolve-pharmacist-id" type="text" placeholder="Optional" />

            <div class="p101-resolve-actions">
              <button id="p101-save-resolution" type="button">Save resolution</button>
              <button id="p101-cancel-resolution" type="button">Cancel</button>
            </div>
            <div id="p101-resolve-feedback" class="p101-resolve-feedback" style="display:none;"></div>
          </div>
        </div>
      </div>
    </section>
  `;

  shadowRoot.appendChild(launcher);
  shadowRoot.appendChild(panelWrap);

  const ui = {
    launcher,
    panelWrap,
    close: panelWrap.querySelector("#p101-close"),
    input: panelWrap.querySelector("#p101-input"),
    source: panelWrap.querySelector("#p101-source"),
    analyze: panelWrap.querySelector("#p101-analyze"),
    feedback: panelWrap.querySelector("#p101-feedback"),
    interpreted: panelWrap.querySelector("#p101-interpreted"),
    result: panelWrap.querySelector("#p101-result"),
    actionBadge: panelWrap.querySelector("#p101-action-badge"),
    actionSummary: panelWrap.querySelector("#p101-action-summary"),
    confidenceTag: panelWrap.querySelector("#p101-confidence-tag"),
    issueLine: panelWrap.querySelector("#p101-issue-line"),
    whyThisMatters: panelWrap.querySelector("#p101-why-this-matters"),
    actionLine: panelWrap.querySelector("#p101-action-line"),
    knownPattern: panelWrap.querySelector("#p101-known-pattern"),
    seenBefore: panelWrap.querySelector("#p101-seen-before"),
    secondary: panelWrap.querySelector("#p101-secondary"),
    documentation: panelWrap.querySelector("#p101-documentation"),
    internalMessage: panelWrap.querySelector("#p101-internal-message"),
    refreshPoints: panelWrap.querySelector("#p101-refresh-points"),
    structuralIssue: panelWrap.querySelector("#p101-structural-issue"),
    historySummary: panelWrap.querySelector("#p101-history-summary"),
    markResolved: panelWrap.querySelector("#p101-mark-resolved"),
    markPending: panelWrap.querySelector("#p101-mark-pending"),
    resolvePanel: panelWrap.querySelector("#p101-resolve-panel"),
    resolveState: panelWrap.querySelector("#p101-resolve-state"),
    resolveNote: panelWrap.querySelector("#p101-resolve-note"),
    resolveScope: panelWrap.querySelector("#p101-resolve-scope"),
    resolvePharmacistId: panelWrap.querySelector("#p101-resolve-pharmacist-id"),
    saveResolution: panelWrap.querySelector("#p101-save-resolution"),
    cancelResolution: panelWrap.querySelector("#p101-cancel-resolution"),
    resolveFeedback: panelWrap.querySelector("#p101-resolve-feedback"),
    copy: panelWrap.querySelector("#p101-copy"),
  };

  let latestAnalysisData = null;
  let latestAnalyzeRequestContext = null;
  let copyResetTimer = null;
  const pendingSavingById = {};
  const pendingById = {};

  const renderPendingButton = (id) => {
    if (pendingSavingById[id]) {
      ui.markPending.textContent = "Saving...";
    } else if (pendingById[id]) {
      ui.markPending.textContent = "Pending";
      ui.markPending.classList.add("is-pending");
    } else {
      ui.markPending.textContent = "Send to Pending";
      ui.markPending.classList.remove("is-pending");
    }
  };

  // Future hook: page-reading/autofill can be added here without changing panel contract.
  const contextAdapter = {
    getPageContext: () => ({ source: "manual-paste" }),
  };

  const buildInterpretedAsText = (result) => {
    if (!result) return "";

    const displayDrug = String(result.drug || "")
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

    const sig = String(result.sig || "").toLowerCase();
    const sigTokens = [];

    if (/\b(four times daily|qid|every\s*6\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("QID");
    else if (/\b(three times daily|tid|every\s*8\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("TID");
    else if (/\b(twice daily|bid|every\s*12\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("BID");
    else if (/\b(nightly|at bedtime|qhs)\b/.test(sig)) sigTokens.push("QHS");
    else if (/\b(once daily|daily|qd|every\s*24\s*(h|hr|hour)s?)\b/.test(sig)) sigTokens.push("QD");

    if (/\b(as needed|prn)\b/.test(sig)) sigTokens.push("PRN");
    if (sigTokens.length === 0) sigTokens.push("Freq Unspecified");

    return [displayDrug, ...sigTokens, `Qty ${result.quantity ?? ""}`].filter(Boolean).join(" | ");
  };

  const buildActionSummary = (actionLine, issueLine) => {
    const source = String(actionLine || issueLine || "").trim();
    if (!source) return "";
    const headerSafe = source
      .replace(/\s*(?:->|→)\s*/g, " ")
      .replace(/\s*\([^)]*confidence[^)]*\)/gi, "")
      .replace(/\s+/g, " ")
      .trim();
    const firstSentence = headerSafe.split(/[.!?]/)[0].trim();
    if (!firstSentence) return source;
    if (firstSentence.length <= 48) return firstSentence;
    return `${firstSentence.slice(0, 47).trim()}...`;
  };

  const buildConfidenceTag = (data) => {
    const history = String(data.history_match_confidence || "").trim().toUpperCase();
    if (history === "HIGH_CONFIDENCE") return "High confidence";
    if (history === "LOW_CONFIDENCE") return "Low confidence";

    const risk = Number(data.risk_score);
    if (Number.isNaN(risk)) return "";
    if (risk >= 70) return "High confidence";
    if (risk >= 40) return "Medium confidence";
    return "Low confidence";
  };

  const setFeedback = (message, type = "ok") => {
    ui.feedback.textContent = message || "";
    ui.feedback.className = "";
    if (!message) {
      ui.feedback.style.display = "none";
      return;
    }
    ui.feedback.style.display = "block";
    if (type === "error") ui.feedback.className = "error";
    if (type === "warn") ui.feedback.className = "warn";
  };

  const setResolveFeedback = (message, type = "ok") => {
    ui.resolveFeedback.textContent = message || "";
    ui.resolveFeedback.className = "p101-resolve-feedback";
    if (!message) {
      ui.resolveFeedback.style.display = "none";
      return;
    }
    if (type === "error") ui.resolveFeedback.classList.add("error");
    if (type === "success") ui.resolveFeedback.classList.add("success");
    ui.resolveFeedback.style.display = "block";
  };

  const resetResolvePanel = () => {
    ui.resolveState.value = "intent_confirmed_sig_unchanged";
    ui.resolveNote.value = "";
    ui.resolveScope.value = "PATIENT_ONLY";
    ui.resolvePharmacistId.value = "";
    setResolveFeedback("");
  };

  const hideResolvePanel = () => {
    ui.resolvePanel.style.display = "none";
    resetResolvePanel();
  };

  const showResolvePanel = () => {
    ui.resolvePanel.style.display = "block";
    setResolveFeedback("");
  };

  const resetActionButtons = () => {
    const id = latestAnalysisData && latestAnalysisData.analysis_id;
    if (id) {
      delete pendingSavingById[id];
      delete pendingById[id];
    }
    ui.markResolved.textContent = "Mark as Resolved";
    ui.markResolved.classList.remove("is-success");
    ui.markResolved.disabled = false;
    ui.markPending.classList.remove("is-pending");
    ui.markPending.disabled = false;
    ui.markPending.textContent = "Send to Pending";
    ui.result.classList.remove("state-pending");
    ui.result.classList.remove("state-resolved");
  };

  const openPanel = () => {
    ui.panelWrap.style.display = "block";
    ui.launcher.style.display = "none";
    ui.input.focus();
  };

  const closePanel = () => {
    ui.panelWrap.style.display = "none";
    ui.launcher.style.display = "block";
  };

  const renderResult = (data) => {
    setFeedback("RENDER HIT");
    
    console.log("RENDER DATA:", {
      lane: data.lane,
      history_match_type: data.history_match_type,
      last_status: data.last_status,
      pattern_assessment: data.pattern_assessment
});

    latestAnalysisData = data;
    const historyMatchType = String(data.history_match_type || "").trim().toUpperCase();
    const laneValue = String(data.lane || "").trim().toUpperCase();
    const knownPatternMessage = String(data.known_pattern_message || "").trim();
    const seenBeforeDisplay = String(data?.seen_before_context?.display || "").trim();

    const isSameRxPassive = laneValue === "PASSIVE" || historyMatchType === "SAME_RX_REFILL_RESOLUTION";
    const isPriorRxHistory = !isSameRxPassive && (historyMatchType === "PRIOR_RX_PATTERN" || !!seenBeforeDisplay);

    ui.result.classList.remove("state-new", "state-passive", "state-prior");
    if (isSameRxPassive) {
      ui.result.classList.add("state-passive");
      ui.actionBadge.textContent = "⚪ KNOWN PATTERN";
      ui.actionSummary.textContent = "Previously clarified on this prescription";
      ui.issueLine.textContent = "";
      ui.whyThisMatters.textContent = "";
      ui.actionLine.textContent = "No further action needed";
      ui.confidenceTag.textContent = "";
      ui.confidenceTag.style.display = "none";
      ui.knownPattern.textContent = "Previously clarified on this prescription";
      ui.knownPattern.style.display = "block";
      ui.seenBefore.textContent = "";
      ui.seenBefore.style.display = "none";
    } else {
      ui.result.classList.add(isPriorRxHistory ? "state-prior" : "state-new");
      ui.actionBadge.textContent = String(data.action_badge || "").replace(/\s*(?:->|→).*$/s, "").trim();
      ui.actionSummary.textContent = buildActionSummary(data.action_line, data.issue_line);
      ui.issueLine.textContent = String(data.issue_line || "");
      ui.whyThisMatters.textContent = String(data.why_this_matters || "");
      ui.actionLine.textContent = String(data.action_line || "");

      const confidenceTag = buildConfidenceTag(data);
      if (confidenceTag) {
        ui.confidenceTag.textContent = `Confidence: ${confidenceTag}`;
        ui.confidenceTag.style.display = "block";
      } else {
        ui.confidenceTag.textContent = "";
        ui.confidenceTag.style.display = "none";
      }

      if (knownPatternMessage && !isPriorRxHistory) {
        ui.knownPattern.textContent = knownPatternMessage;
        ui.knownPattern.style.display = "block";
      } else {
        ui.knownPattern.textContent = "";
        ui.knownPattern.style.display = "none";
      }

      if (isPriorRxHistory && seenBeforeDisplay) {
        ui.seenBefore.textContent = seenBeforeDisplay;
        ui.seenBefore.style.display = "block";
      } else {
        ui.seenBefore.textContent = "No prior history";
        ui.seenBefore.style.display = "block";
      }
    }

    ui.documentation.textContent = data.documentation ? `Documentation: ${data.documentation}` : "Documentation: none";
    ui.internalMessage.textContent = data.internal_message ? `Internal message: ${data.internal_message}` : "Internal message: none";

    const refreshPoints = Array.isArray(data.refresh_points) ? data.refresh_points : [];
    ui.refreshPoints.textContent = refreshPoints.length
      ? `Refresh points: ${refreshPoints.join(" | ")}`
      : "Refresh points: none";

    ui.structuralIssue.textContent = data.structural_issue
      ? `Structural issue: ${data.structural_issue}`
      : "Structural issue: none";

    const historySummary = data.history_summary;
    ui.historySummary.textContent = historySummary
      ? `History summary: ${typeof historySummary === "string" ? historySummary : JSON.stringify(historySummary)}`
      : "History summary: none";

    ui.secondary.open = false;
    hideResolvePanel();
    ui.result.style.display = "block";
  };

  const analyze = async () => {
    const rawText = ui.input.value.trim();
    if (!rawText) {
      setFeedback("Please paste a prescription before analyzing.", "warn");
      return;
    }

    resetActionButtons();

    const ctx = contextAdapter.getPageContext();
    latestAnalyzeRequestContext = {
      raw_text: rawText,
      source_ref: ui.source.value.trim() || ctx?.source || null,
      rx_instance_id: null,
      fill_number: 0,
      patient_id: null,
      prescriber_id: null,
    };

    setFeedback("Analyzing...");
    ui.analyze.disabled = true;

    try {
      const response = await fetch("http://127.0.0.1:8001/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: latestAnalyzeRequestContext.raw_text,
          source_ref: latestAnalyzeRequestContext.source_ref,
          rx_instance_id: latestAnalyzeRequestContext.rx_instance_id,
          fill_number: latestAnalyzeRequestContext.fill_number,
          patient_id: latestAnalyzeRequestContext.patient_id,
          prescriber_id: latestAnalyzeRequestContext.prescriber_id,
        }),
      });

      console.log("RESPONSE STATUS:", response.status);

      const data = await response.json();
      if (!response.ok || data.status === "INVALID") {
        setFeedback(data.error || "Analysis failed.", "error");
        ui.result.style.display = "none";
        ui.interpreted.style.display = "none";
        return;
      }

      setFeedback("Analysis complete.");
      const interpreted = buildInterpretedAsText(data);
      ui.interpreted.textContent = interpreted ? `Interpreted as: ${interpreted}` : "";
      ui.interpreted.style.display = interpreted ? "block" : "none";
      renderResult(data);
    } catch (err) {
      setFeedback("Could not reach analysis server. Make sure it is running on port 8000.", "error");
      ui.result.style.display = "none";
      ui.interpreted.style.display = "none";
    } finally {
      ui.analyze.disabled = false;
    }
  };

  ui.launcher.addEventListener("click", openPanel);
  ui.close.addEventListener("click", closePanel);
  ui.analyze.addEventListener("click", analyze);

  ui.copy.addEventListener("click", async () => {
    const message = ui.actionLine.textContent || "";
    if (!message) return;
    try {
      await navigator.clipboard.writeText(message);
      ui.copy.textContent = "Copied";
      if (copyResetTimer) {
        clearTimeout(copyResetTimer);
      }
      copyResetTimer = setTimeout(() => {
        ui.copy.textContent = "Copy Message";
        copyResetTimer = null;
      }, 1500);
      setFeedback("Clarification message copied.");
    } catch (err) {
      setFeedback("Unable to copy message.", "error");
    }
  });

  ui.markPending.addEventListener("click", async () => {
    const id = latestAnalysisData && latestAnalysisData.analysis_id;
    if (!id) return;
    pendingSavingById[id] = true;
    ui.markPending.disabled = true;
    renderPendingButton(id);
    await new Promise((resolve) => setTimeout(resolve, 350));
    delete pendingSavingById[id];
    pendingById[id] = true;
    ui.result.classList.remove("state-resolved");
    ui.result.classList.add("state-pending");
    renderPendingButton(id);
    ui.markPending.disabled = false;
    setFeedback("Awaiting MD response.");
  });

  ui.markResolved.addEventListener("click", () => {
    if (!latestAnalysisData || !latestAnalysisData.analysis_id) {
      setFeedback("Run an analysis before saving a resolution.", "warn");
      return;
    }
    showResolvePanel();
  });

  ui.cancelResolution.addEventListener("click", () => {
    hideResolvePanel();
  });

  ui.saveResolution.addEventListener("click", async () => {
    if (!latestAnalysisData || !latestAnalysisData.analysis_id) {
      setResolveFeedback("No active analysis result.", "error");
      return;
    }

    const resolutionState = String(ui.resolveState.value || "").trim();
    const note = String(ui.resolveNote.value || "").trim();
    if (resolutionState === "accepted_as_is" && !note) {
      setResolveFeedback("Note is required for Accept as-is.", "error");
      return;
    }

    const rxInstanceId = latestAnalysisData.rx_instance_id || latestAnalyzeRequestContext?.rx_instance_id;
    const patientId = latestAnalysisData.patient_id || latestAnalyzeRequestContext?.patient_id;
    const fillNumber = Number(latestAnalysisData.fill_number ?? latestAnalyzeRequestContext?.fill_number ?? 0);
    const prescriberId = latestAnalysisData.prescriber_id || latestAnalyzeRequestContext?.prescriber_id || null;
    const issueType = latestAnalysisData.issue_type;
    const normalizedFingerprint = latestAnalysisData.normalized_fingerprint;

    if (!rxInstanceId || !patientId || !issueType || !normalizedFingerprint) {
      setResolveFeedback("Missing required fields from current analysis (rx_instance_id, patient_id, issue_type, normalized_fingerprint).", "error");
      return;
    }

    const payload = {
      rx_instance_id: rxInstanceId,
      fill_number: fillNumber,
      normalized_fingerprint: normalizedFingerprint,
      issue_type: issueType,
      patient_id: patientId,
      resolution_state: resolutionState,
      suppression_scope: ui.resolveScope.value || "PATIENT_ONLY",
      prescriber_id: prescriberId,
      note: note || null,
      pharmacist_id: String(ui.resolvePharmacistId.value || "").trim() || null,
    };

    ui.saveResolution.disabled = true;
    ui.cancelResolution.disabled = true;
    ui.markResolved.disabled = true;
    ui.markResolved.textContent = "Saving...";
    setResolveFeedback("Saving...");

    try {
      const response = await fetch(`http://localhost:8000/resolve/${latestAnalysisData.analysis_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok || String(data.status || "").toLowerCase() === "error") {
        ui.markResolved.disabled = false;
        ui.markResolved.textContent = "Mark as Resolved";
        setResolveFeedback(data.error || "Could not save resolution.", "error");
        return;
      }

      setResolveFeedback("Resolution saved.", "success");
      setFeedback("Resolution saved.");
      await analyze();
      ui.result.classList.add("state-resolved");
      ui.markResolved.textContent = "Resolved ✓";
      ui.markResolved.classList.add("is-success");
      ui.markResolved.disabled = true;
      hideResolvePanel();
    } catch (err) {
      ui.markResolved.disabled = false;
      ui.markResolved.textContent = "Mark as Resolved";
      setResolveFeedback("Could not reach resolve endpoint.", "error");
    } finally {
      ui.saveResolution.disabled = false;
      ui.cancelResolution.disabled = false;
    }
  });
})();
