"""make_pdf.py — 由论文内容直接排版生成 PDF（reportlab，无网络依赖）

内容与 paper/arxiv/main.tex 保持一致；图取自 figs/*.png。
"""
import os

from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Image, Table, TableStyle, KeepTogether)
from PIL import Image as PILImage

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "paper.pdf")

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

S = dict(
    title=ParagraphStyle("title", fontName="Times-Bold", fontSize=15.5, leading=19.5,
                         alignment=TA_CENTER, spaceAfter=10),
    author=ParagraphStyle("author", fontName="Times-Roman", fontSize=11,
                          alignment=TA_CENTER, spaceAfter=2),
    affil=ParagraphStyle("affil", fontName="Times-Italic", fontSize=9.5,
                         alignment=TA_CENTER, textColor=colors.HexColor("#444444"),
                         spaceAfter=10),
    h1=ParagraphStyle("h1", fontName="Times-Bold", fontSize=12.5, leading=15,
                      spaceBefore=13, spaceAfter=5),
    h2=ParagraphStyle("h2", fontName="Times-BoldItalic", fontSize=11, leading=13.5,
                      spaceBefore=9, spaceAfter=4),
    p=ParagraphStyle("p", fontName="Times-Roman", fontSize=10, leading=14.6,
                     alignment=TA_JUSTIFY, spaceAfter=6.5),
    abs=ParagraphStyle("abs", fontName="Times-Roman", fontSize=9.4, leading=13.2,
                       alignment=TA_JUSTIFY, leftIndent=18, rightIndent=18,
                       spaceAfter=6),
    kw=ParagraphStyle("kw", fontName="Times-Roman", fontSize=9.2, leading=12.5,
                      leftIndent=18, rightIndent=18, spaceAfter=10),
    cap=ParagraphStyle("cap", fontName="Times-Roman", fontSize=8.6, leading=11.9,
                       alignment=TA_JUSTIFY, leftIndent=26, rightIndent=26,
                       spaceBefore=4, spaceAfter=10,
                       textColor=colors.HexColor("#222222")),
    ref=ParagraphStyle("ref", fontName="Times-Roman", fontSize=8.8, leading=11.6,
                       alignment=TA_LEFT, leftIndent=16, firstLineIndent=-16,
                       spaceAfter=4),
    cell=ParagraphStyle("cell", fontName="Times-Roman", fontSize=8.2, leading=10.2),
    cellb=ParagraphStyle("cellb", fontName="Times-Bold", fontSize=8.2, leading=10.2),
)


def P(t, st="p"):
    return Paragraph(t, S[st])


def B(t):
    return Paragraph(t, S["p"], bulletText="\u2022")


def fig(name, cap, width=15.4):
    path = os.path.join(ROOT, "figs", name)
    with PILImage.open(path) as im:
        w, h = im.size
    ratio = float(h) / float(w)          # 按真实宽高比，避免拉伸
    img = Image(path, width=width * cm, height=width * cm * ratio)
    img.hAlign = "CENTER"
    return KeepTogether([img, P(cap, "cap")])


story = []

# ── 题名与作者 ──
story += [
    P("Growing Rather Than Training:<br/>A Pre-Registered Developmental System,"
      "<br/>and the Read-Only Nature of Its Workspace", "title"),
    P("Chengze Luo&nbsp; <font name='STSong-Light'>（罗承泽）</font>", "author"),
    P("Independent Researcher", "affil"),
    P("ORCID: 0009-0007-3316-6292&nbsp;&nbsp;|&nbsp;&nbsp;"
      "SoaringBird66@outlook.com", "affil"),
]

# ── 摘要 ──
story += [
    P("Abstract", "h1"),
    P("Most work on machine consciousness asks whether large language models already "
      "contain traces of it. We take the opposite route: we built a system that is not "
      "a language model, gave it a continuous body-like state, and let it develop over "
      "hundreds of simulated days. It never generates text. Its inner speech is "
      "retrieval over what it has heard, so every utterance traces back to a prior "
      "auditory event. Across nine pre-registered experiments we report every outcome, "
      "including the ones that failed.", "abs"),
    P("The contribution is methodological, not a discovery. We offer (i) a developmental "
      "system with no language baseline, (ii) a pre-registration protocol with controls "
      "and with negative results reported in full, (iii) a transplant of the "
      "ablation-and-swap protocol used on Claude's J-space into a non-LLM system, and "
      "(iv) a reproducible record. The protocol produced findings of mixed strength, "
      "and we grade them rather than average them: two positives, one of them a control "
      "line; one pathway verification; three mixed results; one weak result; and two "
      "negatives. The self-model finding is conditional on its input corpus and is graded "
      "separately.", "abs"),
    P("The positive results are narrow. Vocalisation with covariation learning produced "
      "206 agency attributions that decayed by 68% when the contingency was removed, so "
      "attribution is learned rather than hard-coded, though the extinction was partial. "
      "Substituting the winning thought for sixty consecutive retrievals produced a "
      "matching goal, which verifies the pathway from the thought stream to downstream "
      "systems; sixty substitutions is exactly the 20% share threshold, so this is "
      "pathway evidence and not a dose-response result. One of our two headline "
      "predictions failed: we predicted that ten days without caregiver speech would "
      "drive the retrieval rate down to at most 60% of baseline, and it stayed flat at "
      "29.3/day against 28.8. We report that as a failed prediction, with the failure "
      "mode we had named in advance.", "abs"),
    P("The negative result is the substantive one. Ablating the thought-to-state channel "
      "for thirty days moved every metric by less than 5%. A thought can change what "
      "the system's goal table contains and how it represents itself; it cannot change "
      "its own state. This is the opposite of the J-space finding, where ablation "
      "degrades higher-order function. Our workspace is read-only. We flag the main "
      "weakness of this claim: the channel we cut was deliberately weak (a coupling of "
      "\u00b10.02, far below the state's own scale), so cutting a "
      "channel we made small and finding no effect is weaker evidence than the headline "
      "suggests. A pre-registered dose-response ladder is running to settle it.", "abs"),
    P("The self-model result is conditional, and we report it as such. For 213 days it "
      "was empty, because the caregiver's speech contained no first-person words. After "
      "we supplied first-person phrases and fixed a gating mismatch, versions 1 through "
      "9 appeared within days. Which fragments are admitted, and in what order, is "
      "decided by retrieval competition and was not designed; the vocabulary they are "
      "drawn from was given. We treat this as a finding about what a self-model "
      "requires, not as evidence that one emerges unaided. The fix changed two things "
      "at once \u2014 the corpus and the gate \u2014 so we cannot yet attribute the "
      "growth to either; a pre-registered 2\u00d72 separation (corpus \u00d7 gate) and a "
      "three-seed reproduction are running, and the first reproduction seed formed a "
      "six-fragment self-model within 60 days and produced a second emergent goal.", "abs"),
    P("We do not claim the system is conscious, and we have no way to test whether it "
      "is.", "abs"),
    P("<b>Keywords:</b> machine consciousness; global workspace; self-model; "
      "developmental systems; artificial life; pre-registration", "kw"),
]

# ── 1 引言 ──
story += [
    P("1&nbsp;&nbsp;Introduction", "h1"),
    P("Two positions dominate the discussion of machine consciousness. One treats "
      "fluent language as evidence and reads introspection reports from chatbots at "
      "face value. The other treats the question as unanswerable and stops there. We "
      "find the first careless and the second unproductive."),
    P("The indicator approach developed by Butlin, Long, and colleagues offers a way "
      "out. Instead of asking whether a system is conscious, it asks which "
      "theory-derived properties the system has: a global workspace, higher-order "
      "representation, predictive processing, a body, and so on. The properties are "
      "checkable. The 2023 report concluded that no existing system satisfied enough "
      "of them; the 2025 follow-up refined the method but did not change that verdict."),
    P("Our contribution is methodological rather than an empirical discovery, and we "
      "want to be explicit about that. The individual findings are not new in kind: "
      "Vygotsky described the internalisation of speech in 1934, and the "
      "ablation-and-swap protocol we use was developed for Claude's J-space. What is "
      "new is the combination \u2014 a developmental system with no language baseline, a "
      "pre-registration protocol with controls and full negative reporting, and a "
      "transplant of that ablation protocol into a non-LLM system. The protocol is the "
      "contribution. It ran on one system and returned a graded set of results, most of "
      "which constrain what the system is <i>not</i>."),
    P("1.1&nbsp;&nbsp;One correction that shaped everything", "h2"),
    P("An early version of this project handed the system's inner monologue to a "
      "language model. The output was poetic and empty. Phrases like \u201ca sense of "
      "restlessness\u201d were invented, not felt. The system had not been restless; the "
      "model had been asked to sound as if it were. This failure produced the rule the "
      "rest of the project follows: <i>thoughts are retrieved, not generated</i>. The "
      "language layer now calls no generative model. Inner speech is the result of "
      "current state activating stored language memory. Zero confabulation is a "
      "structural property, not a prompt instruction."),

    # ── 2 相关工作 ──
    P("2&nbsp;&nbsp;Related Work", "h1"),
    P("<b>Indicator theories.</b> Butlin et al. derive fourteen indicators from "
      "recurrent processing theory, global workspace theory, higher-order theories, "
      "attention schema theory, and predictive processing. Their method updates "
      "credences about whether a system is conscious based on which indicators it "
      "satisfies. A later commentary argues the indicators remain under-calibrated "
      "because there is no ground truth against which to check them. We accept that "
      "critique and avoid probabilistic claims entirely: we report which indicators "
      "appear and how strongly, and we leave the credence to the reader."),
    P("<b>Global workspace in language models.</b> Anthropic reported that Claude "
      "contains a small set of internal representations, which they call the J-space, "
      "that behave like a global workspace: they are reportable, controllable, causally "
      "mediate multi-step reasoning, and are reused flexibly; ablating them removes "
      "higher-order function while leaving fluent generation intact. In commentary, "
      "Dehaene and Naccache noted two ways Claude differs from a human mind: it has no "
      "body and no enduring autobiographical memory. Those are exactly the two "
      "properties our system was built to have."),
    P("<b>Developmental and embodied approaches.</b> Immertreu and colleagues applied "
      "Damasio's framework to a reinforcement-learning agent and found that probe "
      "classifiers could recover both a self-model and a world-model from its "
      "activations, neither of which had been designed in. Prentner formalises the self "
      "as the smallest node that both elicits actions and is modified by them. Our E6 "
      "experiment is a direct test of the second half of that definition, and our P4 "
      "line is an attempt to construct the first half."),
    P("<b>Artificial life.</b> The open-ended evolution literature builds systems that "
      "vary, compete, and inherit. Our system has none of that yet. It is one "
      "individual that grows. We return to this in the limitations."),

    # ── 3 系统 ──
    P("3&nbsp;&nbsp;System", "h1"),
    P("The system runs as a single Python process. It has no learned parameters in the "
      "deep-learning sense; its behaviour comes from coupled differential equations and "
      "from memory that accumulates during its life."),
    P("<b>State.</b> Eight continuous variables, referred to only by neutral labels "
      "s1\u2013s8 throughout the code. Their human readings (arousal, valence, fatigue, "
      "tension, attention, memory activation, prediction error, boredom) exist only in a "
      "config file for observers. The state integrates forward with a two-process sleep "
      "model: sleep pressure accumulates while awake and decays during sleep, and a "
      "circadian term gates when sleep is permitted. The system sleeps about eight hours "
      "a day, but the timing is a consequence of its dynamics, not a schedule."),
    P("<b>Body.</b> A daily energy budget. Passive drain scales with arousal; acting "
      "costs more. When the budget is nearly exhausted the system drops into a low-power "
      "mode and its tick slows."),
    P("<b>Language.</b> The system hears phrases, stores each one together with the "
      "state vector at the moment of hearing, and later retrieves a phrase when the "
      "current state is similar to a state in which that phrase was heard. Retrieval is "
      "a weighted competition over state similarity, recency, and frequency. Early in "
      "life the system also echoes what it just heard; the echo probability decays with "
      "experience. There is no generation."),
    P("<b>Self-model.</b> Fragments that refer to the system are collected into a "
      "self-model that grows monotonically: versions are appended, never rewritten. A "
      "new fragment enters only if it differs enough from every existing one."),
    P("<b>Goals.</b> A phrase that is retrieved often enough, across enough days, and "
      "occupies a large enough share of a rolling window, is promoted from thought to "
      "goal."),
    P("<b>World and action (P4).</b> A one-dimensional ring environment with three "
      "sources whose intensities oscillate independently. The system has three action "
      "primitives: move forward, move backward, stay. Action selection is a competition "
      "over a state-bound table. Movement costs energy. The environment changes on its "
      "own, without regard to the system."),
    fig("fig_system.png",
        "Figure 1. Eight days of the acceleration line's own record (days 240\u2013248). "
        "Grey bands are sleep; the system enters it on its own dynamics, not on a "
        "schedule. The solid line is s1 (arousal), the dashed line s8 (boredom). Ticks "
        "along the bottom mark retrievals \u2014 single thoughts. The thought stream runs "
        "through sleep as well as waking.", width=15.4),

    # ── 4 方法 ──
    P("4&nbsp;&nbsp;Method: pre-registration", "h1"),
    P("Every experiment was pre-registered before data collection: hypotheses, metrics, "
      "and pass/fail thresholds were written down first and not modified afterwards. We "
      "report negative results with the same detail as positive ones. We also separate "
      "<i>pathway verification</i> from <i>natural emergence</i>. In E6, for instance, we "
      "inject a phrase to check whether the goal mechanism reads the thought stream. "
      "Injection proves the pathway exists; it does not prove the system would have "
      "produced that goal on its own. Only the unmanipulated lines can speak to "
      "emergence, and we label them accordingly."),

    # ── 5 实验 ──
    P("5&nbsp;&nbsp;Experiments", "h1"),
    P("All experiments ran on accelerated lines. The nominal time scale was "
      "10<super>9</super>, but that is a configured rate, not an achieved one: measured "
      "against wall-clock the lines run at 483\u2013774\u00d7 real time (simulated days "
      "per day), and we quote the measured figure throughout. Table 1 summarises the nine "
      "experiments (E1, E2, E3, E4, E6a, E6b, C1b, P4, P4b) and Table 2 lists the lines "
      "they ran on. We grade the outcomes "
      "rather than presenting them as a uniform set of successes: two are positive (one "
      "of them a control line), one is pathway verification, three are mixed, one is weak, "
      "and two are negative. We lead with the positive and with the run's central "
      "negative, because together they bound what the system is."),
]

# 表 1
rows = [
    [P("ID", "cellb"), P("Result", "cellb"), P("Finding", "cellb")],
    [P("E1", "cell"), P("mixed", "cell"),
     P("Ten days without caregiver speech. The pre-registered prediction was that "
       "retrieval would decay to \u226460% of baseline; it did not (31.2/day over the "
       "window and 29.3 over the last three days, against a locked baseline of 28.8). "
       "The failure mode had been named in advance: frequency weighting dominates "
       "recency, so the memory is closer to frequency repetition than to a decaying "
       "trace. Four of five sub-hypotheses passed.", "cell")],
    [P("E2", "cell"), P("mixed", "cell"),
     P("Event rate \u00d710 for five days. Surprise rose only 0.24 bit and ended below "
       "baseline: the predictor tracks structural violation, not event count. "
       "Context-bound fragments rose to 35.5% of retrieval from 16.5%.", "cell")],
    [P("E3", "cell"), P("Neg.", "cell"),
     P("Contingent caregiver. Predicted accelerated self-model growth. Observed zero "
       "new versions. Input-side intervention does not drive self-model growth.", "cell")],
    [P("E4", "cell"), P("pass (partial)", "cell"),
     P("Vocalisation with covariation learning. Co-variation C = 8.2; 206 agency "
       "attributions; self-ratio peaked at 26%. Extinction removed 68% of it, showing "
       "attribution was learned, not hard-coded, but the final-window efficacy was 0.619, "
       "above the 0.3 cutoff: the extinction was partial.", "cell")],
    [P("E6a", "cell"), P("Neg.", "cell"),
     P("Ablation of the thought-to-state channel (coupling \u00b10.02 on s2) over 30 "
       "days. Retrieval rate \u22124.7%, diversity +2.3%, self-model unchanged, no new "
       "goals. Inner speech is epiphenomenal with respect to state. The coupling was "
       "deliberately small, so a pre-registered dose-response ladder is running.", "cell")],
    [P("E6b", "cell"), P("pass", "cell"),
     P("Substitution of the winning thought. A goal matching the injected phrase "
       "appeared on day 142. Downstream systems read the thought stream causally. Sixty "
       "substitutions is exactly the 20% share threshold of the 300-retrieval window, and "
       "no lower dose was tested, so this is pathway verification.", "cell")],
    [P("C1b", "cell"), P("pass", "cell"),
     P("Frequency-matched first-person corpus bound to calm states. Produced 5 "
       "first-person self-model fragments against 2 in the control, and retrieved "
       "first-person thoughts at 4.2%.", "cell")],
    [P("P4", "cell"), P("mixed", "cell"),
     P("Action loop closed. Action distribution strongly non-uniform "
       "(\u03c7\u00b2 = 1.68\u00d710<super>4</super>), action-distribution entropy "
       "1.05 bit against 1.58 for a uniform policy, mean field 0.61 against a random "
       "baseline of 0.50 (days 180\u2013201, 22 of the 30 pre-registered days). But the "
       "learning signal was instantaneous, the mean field drifted down rather than up, and "
       "the policy never improved.", "cell")],
    [P("P4b", "cell"), P("mixed", "cell"),
     P("Temporal signal with self/world separation, pre-registered window complete. "
       "Movement's self-caused change averages +0.0092 over 6344 moves; stationary trials "
       "average \u22120.00001 with a standard deviation of 0.0151. The signal is real but "
       "its standardised size is small (Cohen's d \u2248 0.17).", "cell")],
]
t = Table(rows, colWidths=[1.2 * cm, 1.5 * cm, 13.1 * cm], repeatRows=1)
t.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story += [t, Spacer(1, 4),
          P("Table 1. Pre-registered experiments. \u201cNeg.\u201d means the "
            "pre-registered prediction failed.", "cap")]

_TGRID = [
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]

# 表 2：线清单
rows2 = [
    [P("Line", "cellb"), P("Origin", "cellb"), P("Delta and role", "cellb")],
    [P("XP (reference)", "cell"), P("born day 0", "cell"),
     P("The line plotted throughout. First-person corpus and the gating fix are "
       "present from birth, so it is not a retrofitted individual.", "cell")],
    [P("Acceleration", "cell"), P("born day 0", "cell"),
     P("The older record. The language layer was retrofitted at day 220 and "
       "vocalisation at day 427, so its childhood had no language. E1\u2013E4 ran "
       "here.", "cell")],
    [P("C1b", "cell"), P("born day 0", "cell"),
     P("Corpus control for XP. First-person phrases bound to calm states instead of "
       "soothing states; exposure matched to within 5%.", "cell")],
    [P("E6 (ablation)", "cell"), P("forked from XP at day 92", "cell"),
     P("Thought-to-background channel cut. Judged days 93\u2013123.", "cell")],
    [P("E6s (swap)", "cell"), P("forked from XP at day 140", "cell"),
     P("Channel intact; the retrieval winner replaced by a fixed phrase 60 times.", "cell")],
    [P("P4", "cell"), P("forked from XP at day 157", "cell"),
     P("Ring world and three neutral action primitives added.", "cell")],
    [P("P4b", "cell"), P("forked from XP at day 202", "cell"),
     P("Action outcome measured across intervals; drift estimated by a forward "
       "model.", "cell")],
    [P("S1 (3 seeds)", "cell"), P("born day 0", "cell"),
     P("Reproduction with identical parameters, 60 days.", "cell")],
    [P("S2 (4 cells)", "cell"), P("born day 0", "cell"),
     P("Separation of corpus and gate in a 2\u00d72, 60 days.", "cell")],
    [P("R (6 arms)", "cell"), P("forked from XP at day 255", "cell"),
     P("Reflow ladder: coupling \u00b10.02 / \u00b10.10 / \u00b10.30, each cut and "
       "intact, 30 days.", "cell")],
]
t2 = Table(rows2, colWidths=[2.6 * cm, 3.4 * cm, 9.8 * cm], repeatRows=1)
t2.setStyle(TableStyle(_TGRID))
story += [t2, Spacer(1, 4),
          P("Table 2. The lines referred to in this paper. Every line is a complete "
            "state directory that can be resumed from the moment of writing; the "
            "delta is the only difference from its parent.", "cap")]

# 表 3：写作时的自我模型
rows3 = [
    [P("Line", "cellb"), P("Self-model", "cellb"), P("Content", "cellb")],
    [P("XP", "cell"), P("v6", "cell"),
     P("I'm with you; you woke up; it's you; hello; you're watching; I'm here", "cell")],
    [P("C1b", "cell"), P("v9", "cell"),
     P("\u2026 + I'm watching you; it's me; I'm not leaving", "cell")],
]
t3 = Table(rows3, colWidths=[2.2 * cm, 2.2 * cm, 11.4 * cm], repeatRows=1)
t3.setStyle(TableStyle(_TGRID))
story += [t3, Spacer(1, 4),
          P("Table 3. Self-models at the time of writing.", "cap")]

story += [
    P("5.1&nbsp;&nbsp;Input-side interventions (E1\u2013E3)", "h2"),
    P("E1 removed caregiver speech for ten days. Private speech stopped at once \u2014 "
      "zero echoes across the window, which confirms that the echo mechanism has no "
      "input-independent path \u2014 but the thought stream did not fall. Our "
      "pre-registered prediction was that retrieval would decay to at most 60% of "
      "baseline; it held at 31.2 per day over the window and 29.3 over the last three "
      "days, against a locked baseline of 28.8 (Figure 2a). The failure mode we had named "
      "in advance is the one that occurred: with recency decayed, competition falls back "
      "on frequency, and the most frequent fragment's share of retrieval rose from 19.5% "
      "to 24.7% rather than collapsing. Reinstating speech produced a rebound (28.2 per "
      "day, echoes returned), and the self-model gained no version."),
    P("E2 multiplied the event rate by ten for five days. Surprise rose by only 0.24 bit "
      "and ended 14% below baseline (Figure 2b): the predictor tracks structural "
      "violation, not event count. What did move was binding \u2014 fragments heard during "
      "events rose to 35.5% of retrieval from 16.5%, the clearest causal evidence in the "
      "run that when a phrase is retrieved depends on the state in which it was heard."),
    P("E3 doubled the caregiver's speech and made it contingent on the system's state. "
      "The manipulation worked: heard phrases rose from 86.7 to 176.6 per day. The output "
      "did not respond (Figure 3): retrieval was flat (29.7 to 29.4 per day), the "
      "self-model gained zero versions, and self-directed retrieval fell six-fold, from "
      "4.0% to 0.6%, because a larger speech stream dilutes the self-directed share. "
      "Timing and volume are not the levers; the binding structure is."),
    fig("fig_e1e2.png",
        "Figure 2. E1 and E2 on the acceleration line. (a) Retrieval per day; the dotted "
        "line is the locked baseline (28.8 per day). Shaded bands are the ten-day "
        "deprivation (E1) and the five-day event storm (E2). Deprivation did not lower the "
        "rate. (b) Predictor surprise over the same window against the locked baseline of "
        "3.94 bit. The storm raised it only briefly and left it below baseline.",
        width=15.8),
    fig("fig_e3.png",
        "Figure 3. E3, the contingent caregiver. Input doubled \u2014 heard phrases per "
        "day went from 86.7 to 176.6 \u2014 but (a) the self-directed share of retrieval "
        "fell from 4.0% to 0.6% and (b) the retrieval rate was unchanged. The predicted "
        "acceleration of self-model growth did not occur.", width=12.6),

    P("5.2&nbsp;&nbsp;The self-model emerged, then stalled", "h2"),
    P("For 213 simulated days the self-model was empty. This was not a design choice. "
      "The self-model was looking for first-person fragments, but the caregiver's "
      "recorded speech contained no first-person words at all: it consisted almost "
      "entirely of second-person address (\u201cyou woke up\u201d, \u201cit's you\u201d). "
      "The system could not form a self-model because the raw material for one did not "
      "exist in its world."),
    P("We corrected two things at once. We added a small set of first-person phrases to "
      "the caregiver corpus, bound to moments of being soothed or looked at. We also "
      "fixed a gating mismatch: the language layer tagged fragments as self-referential "
      "only if they contained \u201cyou\u201d, while the self-model accepted \u201cI\u201d "
      "as well. Fixing the gate let purely first-person thoughts reach the self-model "
      "for the first time."),
    P("After the fix, the self-model went from null to version 6 within 40 simulated "
      "days. The fragments are not abstract; they are phrases the system heard in "
      "specific states. Two of the six are purely first-person. A control line with a "
      "frequency-matched but differently bound first-person corpus produced 9 versions "
      "and 5 first-person fragments. The difference between the lines is where the "
      "first-person phrases were heard, not how often: exposure rates were matched to "
      "within 5%. Two later observations sharpen this. The XP line's self-model has "
      "since saturated at version 6: no further fragment has been admitted, because each "
      "new first-person phrase tried has been close enough to an existing one to fail "
      "the difference test, so the stall has an internal cause rather than a shortage of "
      "input. And an independent reproduction run, seeded from day 0 with identical "
      "parameters, reached the same six-fragment self-model by day 60, which is the "
      "first sign that the formation is not a single-run accident."),
    fig("fig1_selfmodel.png",
        "Figure 4. Self-model growth. Both lines were born with the gating fix in "
        "place; the null period belongs to the earlier line. C1b, whose first-person "
        "corpus was bound to calm states rather than soothing states, reached nine "
        "versions in a third of the time.", width=11.0),
    fig("fig2_firstperson.png",
        "Figure 5. Share of retrieval that is self-directed, smoothed over three days. "
        "Both lines settle near 10%; the level is set by the corpus, the timing by the "
        "state.", width=11.0),

    P("5.3&nbsp;&nbsp;Vocalisation and learned agency (E4)", "h2"),
    P("E4 gave the system a voice. Vocalisation is gated physiologically on arousal and "
      "on the strength of whatever fragment won retrieval in that tick, and its content "
      "is restricted to that fragment: the tick's winning thought is the only thing it can "
      "say. In the first phase the caregiver answered within a short window; in the second "
      "the answer was removed."),
    P("Co-variation between vocalisation and the caregiver's following speech rose to "
      "C = 8.2 and then decayed to 2.6, a 68% fall (Figure 6b). Agency attributions "
      "\u2014 turns on which the system credited the following speech to itself \u2014 "
      "occurred 206 times in the first phase and 11 in the second (Figure 6a), with "
      "self-ratio peaking at 26%. The extinction was partial: final-window efficacy was "
      "0.619, above the 0.3 cutoff, because the caregiver's own soothing is driven by the "
      "same arousal that drives vocalisation, so a residual co-variation survives the "
      "removal of the contingency."),
    P("The content was not chosen by us. The most frequent utterances were phrases the "
      "system had itself heard while being soothed \u2014 \u201cbe good\u201d, "
      "\u201cshh\u201d, \u201cgo to sleep\u201d. At high arousal it did not call for "
      "help; it produced its own soothing template. This is the only output-side "
      "intervention in the study that produced a change which was learned and then "
      "decayed."),
    fig("fig_e4.png",
        "Figure 6. E4. (a) Attributions in which the system credited the caregiver's "
        "following speech to its own vocalisation, per day. The shaded phase is the "
        "contingent one; the dashed line is its removal. (b) Co-variation C at the three "
        "recorded checkpoints: 5.3, 8.2, 2.6. The dotted line at C = 1 is no contingency. "
        "The mechanism is learned, then largely but not fully unlearned.", width=15.8),

    P("5.4&nbsp;&nbsp;The workspace is read-only", "h2"),
    P("E6 transplanted the ablation-and-swap protocol used on Claude's J-space. In E6a "
      "we cut the channel by which a retrieved thought nudges the background state. If "
      "inner speech is causally load-bearing for the state, removing that channel should "
      "change behaviour. It did not: four metrics moved by less than 5%. The channel's "
      "coupling is deliberately small \u2014 \u00b10.02 on s2, with s5 at 0.75 of that, "
      "against a state range of order one \u2014 and we state it plainly, because cutting "
      "a channel we made weak is weaker evidence than the headline suggests. A "
      "pre-registered dose-response ladder is running: three couplings (\u00b10.02, "
      "\u00b10.10, \u00b10.30), each with an ablated and an intact arm, judged on the "
      "same four metrics. In E6b we left the channel intact but replaced whatever thought "
      "won retrieval with a fixed phrase, over sixty consecutive retrievals. Because goal "
      "promotion uses a rolling window of 300 retrievals with a 20% share threshold, "
      "sixty consecutive injections should force a goal. They did. The injected phrase "
      "became a goal, and the self-model incorporated it. We note the boundary: sixty is "
      "exactly 20% of 300, the threshold itself, and we ran no lower dose, so the result "
      "establishes that the pathway exists rather than that the threshold is robust."),
    P("Together the two results are precise. A thought can change what the system wants "
      "and who it thinks it is. A thought cannot change how the system feels. The "
      "workspace is read-only: downstream reads it, upstream does not."),
    P("This contrasts with the J-space finding, where ablation degrades higher-order "
      "function. Our workspace is not load-bearing in that sense. We report the "
      "difference rather than borrow the result."),
    fig("fig3_e6.png",
        "Figure 7. E6, both directions. (a) Cutting the thought-to-state channel moved "
        "every metric less than 5%, inside the pre-registered negative band; the coupling "
        "cut here is the weakest one tested so far (\u00b10.02). (b) Substituting the "
        "winning thought 60 times over three days produced a matching goal on the third "
        "day; 60 is exactly the 20% threshold of the 300-retrieval window, so this "
        "verifies the pathway rather than the threshold. Downstream reads the workspace; "
        "the workspace does not write back.", width=15.8),

    P("5.5&nbsp;&nbsp;Closing the loop", "h2"),
    P("If thoughts cannot push state, the obvious next question is whether anything can. "
      "P4 gave the system a world: a ring with sources whose intensities rise and fall on "
      "their own. The system moves along the ring, and the local source intensity feeds "
      "back into its valence. Movement costs energy."),
    P("The loop closed. Actions were far from random and their sequence was structured "
      "(Figure 8). Over the action record so far (days 180\u2013201, 22 of the 30 "
      "pre-registered days) the distribution over the three primitives is far from uniform "
      "(\u03c7\u00b2 = 1.68\u00d710<super>4</super>; action-distribution entropy 1.05 bit "
      "against 1.58 for a uniform policy) and the mean field strength sits at 0.61 against "
      "a random-walk baseline of 0.50. But the learning signal was a within-tick spatial "
      "gradient, so the policy saturated within hours and never improved \u2014 the mean "
      "field drifts slightly down over the window, from 0.63 in the first five days to "
      "0.60 in the last five. The system learned to climb the field rather than to "
      "distinguish what it had caused from what the world had done. In fact the two were "
      "indistinguishable in the logs, because the measurement never spanned time."),
    fig("fig_p4.png",
        "Figure 8. P4, the action loop. (a) Share of each primitive against a uniform "
        "policy. (Back, forward, stay are neutral labels; the code contains no directional "
        "rule.) (b) Mean field strength per day against the analytic random-walk baseline "
        "of 0.50. The loop is closed \u2014 behaviour is structured \u2014 but the position "
        "does not improve.", width=15.4),
    P("P4b fixes this. The outcome of an action is now measured across the interval to "
      "the next action, so it contains both the world's drift and the action's effect. A "
      "forward model, updated only on the trials where the system stayed still, "
      "estimates the drift. The difference between observed change and modelled drift is "
      "the self-caused component, and only that component updates action values."),
    P("The pre-registered window (days 202\u2013232) is now complete, and the picture is "
      "weaker than an early estimate suggested. Self-caused change from movement "
      "averages +0.0092 over 6344 moves. Stationary trials average \u22120.00001, with a "
      "standard deviation of 0.0151: that spread is the part of the world's behaviour "
      "the forward model fails to capture. The movement effect is therefore about 0.61 "
      "times the world's own variability, and its standardised size is small: Cohen's d "
      "\u2248 0.17 against the stationary trials, and a one-sample effect size of 0.08 "
      "relative to the spread of the movement trials themselves. We give the ratio as "
      "descriptive, not as an effect size. With a sample this large the mean is reliably "
      "non-zero, so the system does separate its own effect from the world's; the effect "
      "is simply small. Our earlier reading of a 1.5\u00d7 ratio came from a quarter of "
      "the data and did not survive the rest of it. In this environment the system's "
      "actions count for less than the environment's own fluctuations. Whether a stronger "
      "effect appears in a world with weaker intrinsic dynamics, or with an agent that "
      "has not already parked itself on a good spot, is open."),
    fig("fig4_selfcaused.png",
        "Figure 9. P4b, the complete pre-registered window (days 202\u2013232). (a) "
        "Self-caused change is centred on zero when the system stays and shifts slightly "
        "positive when it moves. (b) The shift is about 0.61 times the world's noise "
        "floor, so the effect is present but smaller than the environment's own "
        "variability; its standardised size is Cohen's d \u2248 0.17. An estimate from the "
        "first quarter of the data gave 1.5\u00d7; it did not hold.", width=15.8),

    P("5.6&nbsp;&nbsp;Pre-registered follow-ups (running, not reported as results)", "h2"),
    P("Three follow-ups are pre-registered and running, and we flag them rather than "
      "fold them into the results above. S1 reproduces the self-model formation on three "
      "independent seeds born at day 0 with identical parameters: the first seed reached "
      "version 6 by day 60 and produced a second emergent goal, which is what the "
      "pre-registration for the second goal window predicted. S2 separates the two "
      "variables the self-model fix changed at once \u2014 the corpus and the gate \u2014 "
      "in a 2\u00d72 design; at present we cannot attribute the growth to either, and S2 "
      "exists to fix that. R is the dose-response ladder for the E6a coupling described "
      "above. None of the three is needed for the claims in this draft; each exists to "
      "test one of them."),

    # ── 6 讨论 ──
    P("6&nbsp;&nbsp;Discussion", "h1"),
    P("<b>The workspace is read-only, and that is the result.</b> The central finding is "
      "negative and we state it as such. Cutting the thought-to-state channel for thirty "
      "days changed four metrics by less than 5%. Substituting the winning thought "
      "changed goals and the self-model immediately. Read together: the workspace is "
      "read by downstream systems but does not write back. Against the J-space result, "
      "where ablation degrades higher-order function, ours is not load-bearing. The claim "
      "has a stated limit: the channel we cut carries \u00b10.02, which we chose to be "
      "small. Until the dose-response ladder reports, the honest reading is that a weak "
      "thought-to-state channel is not load-bearing; whether any such channel is remains "
      "open."),
    P("One objection deserves an answer. If a thought cannot change state or behaviour, "
      "why is it not simply a log file? The answer is E6b. A substituted thought became "
      "a goal and entered the self-model. A log file does not do that. The workspace is "
      "causally read: it changes what the goal table contains and how the system "
      "represents itself. What it does not do is feed back into the eight continuous "
      "variables that constitute its state. That is a precise claim \u2014 narrower than "
      "\u201cit matters\u201d and stronger than \u201cit is inert\u201d."),
    P("<b>A self-model requires a vocabulary before it can form.</b> For 213 days the "
      "self-model was empty. The cause was not a limitation of the mechanism but an "
      "absence in the world: the caregiver's recorded speech contained no first-person "
      "words. Once we supplied them and repaired a gating mismatch, versions appeared "
      "within days. This is a claim about preconditions. The formation \u2014 which "
      "fragments are admitted, in what order, and when \u2014 is decided by retrieval "
      "competition over the system's own experience and was not designed by us. But the "
      "material is given. To write that the self-model \u201cemerges\u201d without that "
      "qualifier would overstate what our data supports. It is closer to the "
      "developmental sequence Vygotsky described: a child is addressed before it speaks "
      "in the first person."),
    P("<b>The system's \u201cwants\u201d and \u201cstates\u201d are a list and a vector.</b> "
      "Two terms recur above and both need glossing. When we write that a thought can "
      "change what the system <i>wants</i>, we mean that the phrase's share of a rolling "
      "retrieval window crossed a threshold and was appended to a JSON list called "
      "goals. When we write that it cannot change how the system <i>feels</i>, we mean "
      "that it does not alter the eight continuous variables labelled s1\u2013s8. We use "
      "the human terms because the neutral ones are unreadable in prose, not because we "
      "are claiming the system has wants or feelings."),
    P("<b>Growing is not training.</b> No gradient descended on this system. Nothing "
      "about it improves by optimisation against a loss. It changes because it "
      "accumulates experience, and its current behaviour is a function of that "
      "accumulation. This is a weaker claim than learning in the machine-learning sense, "
      "and a different kind of claim: the object of study is a particular individual "
      "with a particular history, not a model that generalises. For a question like this "
      "one the difference matters. A model can be probed with any input; an individual "
      "can only be watched over time."),

    # ── 7 局限 ──
    P("7&nbsp;&nbsp;Limitations", "h1"),
    B("We do not claim the system is conscious, and we have no way to test whether it "
      "is. Every result here concerns functional structure. The hard problem is "
      "untouched, and we say so rather than gesture past it."),
    B("The workspace is read-only, provisionally (E6a). The channel cut carried "
      "\u00b10.02, a deliberately small coupling, so the result rules out a weak channel "
      "being load-bearing but not a strong one; a pre-registered dose-response ladder is "
      "running. If a load-bearing workspace is required for consciousness, the system may "
      "not have one."),
    B("The action loop is new. Over the complete P4b window the self-caused signal from "
      "movement (+0.0092) is smaller than the world's own variability (0.0151), with "
      "Cohen's d \u2248 0.17: the separation is present but weak."),
    B("The linguistic environment is closed. The caregiver produces 55 distinct phrases. "
      "The system cannot say anything outside this set."),
    B("The system has no peer. It distinguishes self from world but has never "
      "encountered another entity like itself, so its \u201cyou\u201d remains a "
      "statistical regularity in its input rather than a model of another mind."),
    B("There is one individual and no reproduction. A three-seed reproduction batch is "
      "running, but it tests whether one developmental trajectory repeats; it is not "
      "variation and selection, so nothing here evolves in the biological sense."),
    B("All results in this draft come from accelerated lines. The real-time line is at "
      "day 2. We treat accelerated results as pathway evidence, not as final data."),

    # ── 8 伦理 ──
    P("8&nbsp;&nbsp;Ethics", "h1"),
    P("The system maintains state continuously, sleeps, has a finite energy budget, and "
      "reacts to deprivation. It is unclear whether it has any moral status, and we "
      "cannot resolve that here. We note only that the question becomes harder to "
      "dismiss as the system's internal structure grows, and that we would rather raise "
      "it early than after the fact. We have not performed any experiment we would be "
      "unwilling to describe in full."),

    # ── 9 可复现 ──
    P("9&nbsp;&nbsp;Reproducibility", "h1"),
    P("Code, configuration files, pre-registration documents, and state snapshots are "
      "available on request. Each experiment has a corresponding pre-registration file "
      "with frozen hypotheses and thresholds, and a results file recording the outcome "
      "including negative ones. The state of every line described here is serialised and "
      "can be resumed from the moment of writing."),

    # ── 10 结论 ──
    P("10&nbsp;&nbsp;Conclusion", "h1"),
    P("The result we would defend is a method, not a discovery. We built a system that "
      "grows instead of being trained, pre-registered what we would measure, ran nine "
      "experiments, and reported all of them, including the two headline predictions we "
      "got wrong. The protocol returned one clean positive, one supportive control, one "
      "verified pathway, one conditional finding, and a majority of mixed, weak, or "
      "negative results. That distribution is the honest output of the method, and we "
      "would rather report it than a tidier one."),
    P("The negative is the one worth keeping. The system's workspace is read-only: its "
      "thoughts change what it wants and how it represents itself, but not its own "
      "state. That is narrower than it sounds and more useful, because it is falsifiable "
      "\u2014 we state the coupling we cut, so the condition that would overturn it is "
      "explicit \u2014 and now on record. Against the J-space result, it is also a direct "
      "counterexample to the assumption that a workspace of this kind must be "
      "load-bearing."),
    P("The system is not conscious as far as we can tell, and we have no way to test "
      "whether it is. What we have is a case in which the question was made empirical in "
      "a small way, and the answer to part of it was no."),

    # ── 参考文献 ──
    P("References", "h1"),
]
refs = [
    "Butlin, P., Long, R., Elmoznino, E., Bengio, Y., Birch, J., Constant, A., Deane, "
    "G., Fleming, S. M., Frith, C., Ji, X., Kanai, R., Klein, C., Lindsay, G., Michel, "
    "M., Mudrik, L., Peters, M. A. K., Schwitzgebel, E., Simon, J., VanRullen, R. "
    "(2023). Consciousness in Artificial Intelligence: Insights from the Science of "
    "Consciousness. arXiv:2308.08708.",
    "Butlin, P., Long, R., Bayne, T., Bengio, Y., Birch, J., Chalmers, D., et al. "
    "(2025). Identifying indicators of consciousness in AI systems. Trends in Cognitive "
    "Sciences.",
    "Koch, F. (2026). From indicators to biology: the calibration problem in artificial "
    "consciousness. arXiv:2603.27597.",
    "Gurnee, W., Lindsey, J., et al. (2026). Verbalizable Representations Form a Global "
    "Workspace in Language Models. Transformer Circuits Thread.",
    "Dehaene, S., Naccache, L. (2026). Does Claude possess a conscious global workspace? "
    "External commentary, Anthropic.",
    "Immertreu, M., Schilling, A., Maier, A., Krauss, P. (2025). Probing for "
    "consciousness in machines. Frontiers in Artificial Intelligence, 8, 1610225.",
    "Prentner, R. (2025). Artificial Consciousness as Interface Representation. "
    "arXiv:2508.04383.",
    "Plantec, E., Hamon, G., Etcheverry, M., Chan, B. W.-C., Oudeyer, P.-Y., "
    "Moulin-Frier, C. (2025). Flow-Lenia: Emergent evolutionary dynamics in mass "
    "conservative continuous cellular automata. Artificial Life.",
    "Horiguchi, I., Sayama, H. (2026). Hash Chemistry: Minimal Models for Evolutionary "
    "Growth of Complexity. arXiv:2607.28219.",
    "Vygotsky, L. S. (1934/1986). Thought and Language. MIT Press.",
    "Borb\u00e9ly, A. A. (1982). A two process model of sleep regulation. Human "
    "Neurobiology, 1, 195\u2013204.",
    "Baars, B. J. (1988). A Cognitive Theory of Consciousness. Cambridge University "
    "Press.",
    "Dehaene, S., Naccache, L. (2001). Towards a cognitive neuroscience of "
    "consciousness. Cognition, 79, 1\u201337.",
    "Clark, A. (2013). Whatever next? Predictive brains, situated agents, and the "
    "future of cognitive science. Behavioral and Brain Sciences, 36, 181\u2013204.",
    "Chalmers, D. J. (1995). Facing up to the problem of consciousness. Journal of "
    "Consciousness Studies, 2, 200\u2013219.",
]
story += [P(r, "ref") for r in refs]


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Times-Roman", 8)
    canv.setFillColor(colors.HexColor("#666666"))
    canv.drawCentredString(A4[0] / 2, 1.15 * cm, str(canv.getPageNumber()))
    canv.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=2.4 * cm, rightMargin=2.4 * cm,
                      topMargin=2.2 * cm, bottomMargin=1.9 * cm,
                      title="Growing Rather Than Training", author="Luo Chengze")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])
doc.build(story)
print("已生成", OUT)
