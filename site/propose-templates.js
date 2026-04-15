/**
 * Starter templates for Propose a Wager (main site + Resonance Exchange).
 * Profiles: `default` (main `propose-a-wager.html`) and `resonance` (`data-propose-profile`
 * on Resonance/Microwonk pages only — alternate proposition placeholders; does not affect main site).
 * Loaded before propose-wager.js; exposes globalThis.ParamutuelProposeTemplates.
 * Node: require("./site/propose-templates.js") for tests.
 */
(function () {
  "use strict";

  var g = typeof globalThis !== "undefined" ? globalThis : this;

  /** @type {Record<string, Record<string, string>>} */
  var PLACEHOLDERS = {
    yesno: {
      default:
        "Will the observable event you care about resolve to Yes before the betting window ends? Replace this with your own yes-or-no question (what counts as Yes must be clear to bettors and resolver).",
      resonance:
        "Will the next public broadcast or archival signal reference stewardship, the Mirabilisk line, or a named steward before betting closes? (Edit to match what observers can verify on-chain or in published channels.)",
    },
    pick: {
      default:
        "Which outcome will occur first among the listed options? Replace this question and rename the options below so the winning line is unambiguous.",
      resonance:
        "Which listed faction, force, or signal crosses the documented perimeter or threshold first in the public record? Rename options to match your scenario.",
    },
    timed: {
      default:
        "When the scheduled event concludes, which result applies? Replace with your match, launch, vote, or release — use the outcome labels for Home/Away/Draw or your own buckets.",
      resonance:
        "When the broadcast window for the contested event settles, which tally or designation matches the published result? Adjust outcome labels to your diegetic framing.",
    },
    freeform: {
      default:
        "What exact short text will appear first in the relevant public announcement? Bettors will type their own answers; you must resolve with the exact winning UTF-8 string.",
      resonance:
        "What exact phrase will appear in the next dispatch on the public channel? Bettors type their own answers; you resolve by publishing the winning string verbatim.",
    },
  };

  /** @type {Record<string, { outcomes: string[], bettingClose: number, resolution: number, freeform: boolean, cardTitle: string, cardBlurb: string }>} */
  var CORE = {
    yesno: {
      outcomes: ["Yes", "No"],
      bettingClose: 2 * 60 * 60,
      resolution: 24 * 60 * 60,
      freeform: false,
      cardTitle: "Yes / No",
      cardBlurb: "Binary question — two outcomes. Fastest path for simple forecasts.",
    },
    pick: {
      outcomes: ["Option A", "Option B", "Option C"],
      bettingClose: 2 * 60 * 60,
      resolution: 24 * 60 * 60,
      freeform: false,
      cardTitle: "Pick one",
      cardBlurb: "Three or more labeled outcomes; exactly one winner (single-outcome tickets).",
    },
    timed: {
      outcomes: ["Home / Side A", "Away / Side B", "Draw / Tie", "Postponed or void"],
      bettingClose: 7 * 24 * 60 * 60,
      resolution: 48 * 60 * 60,
      freeform: false,
      cardTitle: "Timed event",
      cardBlurb: "Longer windows for matches, launches, or votes; includes a postpone/void bucket.",
    },
    freeform: {
      outcomes: [],
      bettingClose: 24 * 60 * 60,
      resolution: 72 * 60 * 60,
      freeform: true,
      cardTitle: "Freeform",
      cardBlurb: "Bettors type answers; you resolve by choosing the exact winning string.",
    },
  };

  function getResolvedTemplate(id, profileKey) {
    var c = CORE[id];
    if (!c) {
      throw new Error("Unknown propose template: " + id);
    }
    var pk = profileKey || "default";
    var ph = PLACEHOLDERS[id] && PLACEHOLDERS[id][pk];
    if (!ph) {
      ph = PLACEHOLDERS[id].default;
    }
    return {
      id: id,
      outcomes: c.outcomes.slice(),
      bettingClose: c.bettingClose,
      resolution: c.resolution,
      freeform: c.freeform,
      placeholderProposition: ph,
      cardTitle: c.cardTitle,
      cardBlurb: c.cardBlurb,
    };
  }

  function listTemplateIds() {
    return Object.keys(CORE);
  }

  var api = {
    getResolvedTemplate: getResolvedTemplate,
    listTemplateIds: listTemplateIds,
  };

  g.ParamutuelProposeTemplates = api;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})();
