(function () {
  "use strict";
  function reviewStatus(result = {}, artifacts = {}, steps = [], version) {
    const verification = result.verification || {}, final = artifacts.final;
    version ||= final?.version || verification.article_version || (artifacts["draft:2"] ? 2 : 1);
    const review = artifacts[`review:${version}`] || verification.judge || {};
    const step = steps.find(s => s.step === (version === 1 ? "judge" : "rejudge"));
    const remaining = final?.remaining || verification.remaining || [];
    const overall = review.overall || "not_reviewed";
    const incomplete = ["not_reviewed", "incomplete"].includes(overall);
    const budget = result.budget?.exhausted || /预算/.test(step?.detail?.error || "") || remaining.some(s => /预算/.test(s));
    if (incomplete) {
      const seconds = result.budget?.limit_seconds || 90;
      const reason = budget ? `${seconds} 秒总预算已结束，自动评审未能返回完整结论。` : step?.detail?.error || review.pending_confirm?.[0] || (overall === "incomplete" ? "自动评审未覆盖全部文段，尚无完整审核结论。" : "自动评审尚未返回结论。");
      return {state:"incomplete",label:"自动评审未完成",detail:reason,passed:false,needsReview:true};
    }
    const problems = review.problems || [];
    if (!["pass", "ok"].includes(overall)) return {state:"needs_fix",label:"自动评审发现问题",detail:problems[0]?.detail || "自动评审未通过，请查看具体问题。",passed:false,needsReview:true};
    if (remaining.length || final?.state === "needs_review") return {state:budget ? "incomplete" : "needs_fix",label:budget ? "修订或复核未完成" : "有待核对项",detail:remaining.find(s=>!s.includes("独立评审未通过或未完成")) || "请核对尚未解决的问题。",passed:false,needsReview:true};
    return {state:"passed",label:"自动核验通过",detail:"规则检查与自动评审已完成。",passed:true,needsReview:false};
  }
  if (typeof module !== "undefined" && module.exports) module.exports=reviewStatus;
  else window.processReviewStatus=reviewStatus;
})();
