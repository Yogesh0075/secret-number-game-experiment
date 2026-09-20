"""The Secret Number: pass-and-play on one phone.  Run:  streamlit run app.py"""
import streamlit as st

import game_engine as ge
import tracking

st.set_page_config(page_title="The Secret Number", page_icon="🔢", layout="centered")
S = st.session_state

st.markdown(
    """
<style>
.clue{border:2px solid rgba(128,128,128,.55);border-radius:6px;padding:1.2rem 1rem;
      margin:.6rem 0 1rem;font-size:1.65rem;line-height:1.25;font-weight:600;text-align:center}
.who{font-size:2.2rem;font-weight:700;line-height:1.1;margin:.2rem 0 .8rem}
</style>
""",
    unsafe_allow_html=True,
)


def goto(stage, **state):
    S.stage = stage
    for k, v in state.items():
        S[k] = v
    st.rerun()


def start_game(players, hi):
    S.game = ge.new_game(players, hi=hi)
    S.gid = S.get("gid", 0) + 1  # keeps widget keys unique per game
    S.round, S.idx, S.bluffing = 0, 0, False
    S.celebrated = False
    goto("clue_handoff")


def round_caption():
    r = S.round
    st.progress((r + 1) / ge.ROUNDS, text=f"Round {r + 1} of {ge.ROUNDS}")
    st.caption(f"Round {r + 1} of {ge.ROUNDS} · {ge.ROUND_TIERS[r]} clues")


def round_mood(r):
    return (
        "Warm-up round: listen for the broad direction of each clue.",
        "Getting closer: small details and patterns matter more now.",
        "Final stretch: trust your instincts, but a convincing bluff can still fool you.",
    )[r]


def score_explanation(g, r, player):
    """A human-friendly explanation of a player's round result."""
    target = g.votes[r][player]
    received = g.fingers[r][player]
    parts = []
    if target is None:
        parts.append("called the other clue a bluff")
    elif target in g.bluffed[r]:
        parts.append("trusted a bluff")
    else:
        parts.append("trusted an honest clue (+1)")

    if player in g.bluffed[r]:
        if received:
            parts.append(f"their bluff fooled {received} player{'s' if received != 1 else ''} (+{received * ge.FOOLED_POINTS})")
        else:
            parts.append("their bluff fooled nobody (-1)")
    elif received:
        parts.append(f"their honest clue was trusted by {received} player{'s' if received != 1 else ''} (+{received})")
    return "; ".join(parts) + "."


def confirmed_candidate_count(g, through_round):
    """Count numbers matching the clue statements now known to be honest."""
    candidates = set(range(g.low, g.high + 1))
    for r in range(through_round + 1):
        for player in g.players:
            if player not in g.bluffed[r]:
                candidates &= g.clues[r][player].matches
    return len(candidates)


# ---------------------------------------------------------------- login ----
def screen_login():
    st.title("The Secret Number")
    st.subheader("Choose a username to play")
    st.caption("This name is only saved for the current browser session.")
    username = st.text_input("Username", max_chars=30, key="login_username")
    if st.button("Continue", type="primary", use_container_width=True, disabled=not username.strip()):
        if tracking.sign_in(username):
            st.rerun()


# ---------------------------------------------------------------- setup ----
def screen_setup():
    st.title("The Secret Number")
    st.write(
        "Work out one secret number together—but watch out, because one clue "
        "may be a bluff."
    )
    st.info(
        "How it works: read your private clue aloud without showing the card, "
        "compare it with the other clues, decide whose clue you believe, and then make your final guess. "
        "Each player can bluff once in the whole game."
    )
    with st.form("setup"):
        count = st.slider("Players", ge.MIN_PLAYERS, 15, 5)
        raw = st.text_area(
            "Names, one per line (optional)", height=120, placeholder="Asha\nBen\nChen"
        )
        hi = st.select_slider(
            "Number range", options=[50, 100, 200], value=100, format_func=lambda v: f"1 to {v}"
        )
        go = st.form_submit_button("Start game", type="primary", use_container_width=True)
    if go:
        typed = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        n = max(count, len(typed))
        players = typed + [f"Player {i}" for i in range(len(typed) + 1, n + 1)]
        try:
            start_game(players, hi)
        except ValueError as e:
            st.error(str(e))


# --------------------------------------------------------- clue passing ----
def screen_clue_handoff():
    g, p = S.game, S.game.players[S.idx]
    round_caption()
    st.info(round_mood(S.round))
    st.subheader("Your private clue")
    st.write("Pass the phone to")
    st.markdown(f'<div class="who">{p}</div>', unsafe_allow_html=True)
    st.write("Everyone else, look away.")
    if st.button(f"I'm {p}. Show my clue", type="primary", use_container_width=True):
        goto("clue_view", bluffing=False)


def next_after_clue():
    S.idx += 1
    if S.idx >= len(S.game.players):
        goto("speak", idx=0)
    goto("clue_handoff", bluffing=False)


def screen_clue_view():
    g, r = S.game, S.round
    p = g.players[S.idx]
    clue = g.clue_seen(r, p)
    round_caption()
    st.markdown(f'<div class="who">{p}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="clue">{clue.text}</div>', unsafe_allow_html=True)
    if S.bluffing:
        st.warning("Bluff active. Describe this clue as if it were true—only you know it is false.")
        if st.button("Hide and pass the phone", type="primary", use_container_width=True):
            next_after_clue()
        return
    if st.button("I remember it — hide and pass", type="primary", use_container_width=True):
        next_after_clue()
    can = g.can_bluff(r, p)
    if st.button(
        f"Swap this for my bluff ({g.bluffs_left[p]} left)", disabled=not can, use_container_width=True
    ):
        g.use_bluff(r, p)
        S.bluffing = True
        st.rerun()
    if not can:
        st.caption(g.bluff_block_reason(r, p))
    else:
        st.caption("A bluff swaps this card for a false clue. You get one bluff for the whole game.")


# ------------------------------------------------------------ talk/vote ----
def screen_speak():
    g, r = S.game, S.round
    round_caption()
    st.header("Say it")
    st.write(
        "When your name appears, read your clue exactly as it is written. "
        "Do not show the card to anyone. If you chose to bluff, read the false "
        "clue exactly the same way."
    )
    st.info(
        "Listen for clues that fit together. If one statement does not match the "
        "others, that player may be bluffing."
    )
    for i, name in enumerate(g.speak_orders[r], 1):
        st.write(f"{i}. {name}")
    st.subheader("Evidence Board")
    st.write(
        "As each player reads their statement, one person writes it below. "
        "The honest statements should all fit one number; a bluff points to a different answer."
    )
    st.text_area(
        "Evidence Board",
        height=120,
        key=f"notes_{S.gid}",
        placeholder="Example: More than 20; last digit 1; divides equally by 31.",
    )
    st.caption("Keep this board for the final guess. It is a player aid only; it never changes scoring or reveals the answer.")
    if st.button("Everyone has spoken", type="primary", use_container_width=True):
        goto("point")


def screen_point():
    g, r = S.game, S.round
    round_caption()
    two_players = len(g.players) == 2
    st.header("Who do you believe?")
    if two_players:
        st.write(
            "Each player now decides whether the other person's clue sounds true "
            "or like a bluff. Keep your decision private until both choices are entered."
        )
    else:
        st.write(
            "Each player quietly chooses the one person whose clue sounds most believable. "
            "Do not discuss your choices before everyone has decided."
        )
    st.caption(
        "Choose the clue that best fits the group notes. Trust an honest clue: you both get +1. "
        "Trust a bluff: the bluffer gets +2. If nobody trusts a bluffer, they lose 1 point."
    )
    with st.form(f"point_{S.gid}_{r}"):
        picks = {}
        decisions_recorded = {}
        for p in g.players:
            others = [q for q in g.players if q != p]
            if two_players:
                trust_choice = f"I trust {others[0]}'s clue"
                choice = st.selectbox(
                    f"{p}'s decision",
                    [trust_choice, "I think they are bluffing"],
                    index=None,
                    placeholder="Choose privately",
                    key=f"pt_{S.gid}_{r}_{p}",
                )
                picks[p] = others[0] if choice == trust_choice else None
                decisions_recorded[p] = choice is not None
            else:
                picks[p] = st.selectbox(
                    f"{p} believes",
                    others,
                    index=None,
                    placeholder="Choose a player",
                    key=f"pt_{S.gid}_{r}_{p}",
                )
        go = st.form_submit_button("Reveal", type="primary", use_container_width=True)
    if go:
        if not two_players and any(v is None for v in picks.values()):
            st.error("Choose the clue each player believes.")
        elif two_players and not all(decisions_recorded.values()):
            st.error("Record a decision for both players.")
        else:
            g.score_round(r, picks)
            goto("reveal")


def leaderboard_rows(g):
    trust = g.trust_points()
    return [{"Player": p, "Trust points": trust[p]} for p, _ in sorted(trust.items(), key=lambda kv: (-kv[1], kv[0]))]


def screen_reveal():
    g, r = S.game, S.round
    bl = g.bluffed[r]
    round_caption()
    st.header("Reveal")
    if bl:
        st.warning("Bluffed this round: " + ", ".join(sorted(bl)))
    else:
        st.success("Nobody bluffed this round.")
    st.dataframe(
        [
            {
                "Player": p,
                "Trusted": g.votes[r][p] or "Nobody (called bluff)",
                "Trusted by": g.fingers[r][p],
                "Points": g.round_points[r][p],
                "Said": "bluff" if p in bl else "honest",
            }
            for p in g.players
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.subheader("Trust points so far")
    st.dataframe(leaderboard_rows(g), hide_index=True, use_container_width=True)
    remaining = confirmed_candidate_count(g, r)
    st.info(
        f"Case update: the confirmed honest clues so far leave {remaining} "
        f"possible number{'s' if remaining != 1 else ''}. Keep building the Evidence Board."
    )
    with st.expander("Why did the scores change?"):
        for p in g.players:
            st.write(f"**{p}:** {score_explanation(g, r, p)}")
    last = r + 1 >= ge.ROUNDS
    if st.button("Final guess" if last else "Next round", type="primary", use_container_width=True):
        if last:
            goto("final_handoff", idx=0)
        goto("clue_handoff", round=r + 1, idx=0, bluffing=False)


# ---------------------------------------------------------- final guess ----
def screen_final_handoff():
    g, p = S.game, S.game.players[S.idx]
    st.caption("Final guess")
    st.write("Pass the phone to")
    st.markdown(f'<div class="who">{p}</div>', unsafe_allow_html=True)
    st.write("Everyone else, look away.")
    if st.button(f"I'm {p}. Pick my number", type="primary", use_container_width=True):
        goto("final_pick")


def screen_final_pick():
    g = S.game
    p = g.players[S.idx]
    st.caption("Final guess")
    st.markdown(f'<div class="who">{p}</div>', unsafe_allow_html=True)
    st.write("Use the clues your group collected. Which number fits them best?")
    if S.get(f"notes_{S.gid}", "").strip():
        st.text_area(
            "Evidence Board",
            value=S[f"notes_{S.gid}"],
            height=120,
            disabled=True,
            key=f"final_notes_{S.gid}_{p}",
        )
    choice = st.radio("Options", g.options, index=None, horizontal=True, key=f"pick_{S.gid}_{p}", label_visibility="collapsed")
    if st.button("Lock it in", type="primary", use_container_width=True, disabled=choice is None):
        g.submit_pick(p, choice)
        S.idx += 1
        if S.idx >= len(g.players):
            goto("results")
        goto("final_handoff")


# -------------------------------------------------------------- results ----
def screen_results():
    g = S.game
    if not S.get("celebrated"):
        st.balloons()
        S.celebrated = True

    winners = g.winners()
    st.title("Results")
    st.write(f"The secret number was **{g.secret}**.")
    st.success(("Winner: " if len(winners) == 1 else "Tied winners: ") + ", ".join(winners))

    trust, guess = g.trust_points(), g.guess_points()
    st.dataframe(
        [
            {
                "Player": p,
                "Trust": trust[p],
                "Guess": g.picks[p],
                "Guess pts": guess[p],
                "Total": total,
            }
            for p, total in g.leaderboard()
        ],
        hide_index=True,
        use_container_width=True,
    )
    reads, fools = g.good_reads(), g.bluff_fools()
    best_reads = max(reads.values())
    if best_reads:
        detectives = [p for p, score in reads.items() if score == best_reads]
        st.info(
            "Sharpest reader: " + ", ".join(detectives) +
            f" ({best_reads} honest clue{'s' if best_reads != 1 else ''} spotted)"
        )
    best_fools = max(fools.values())
    if best_fools:
        bluffers = [p for p, score in fools.items() if score == best_fools]
        st.warning(
            "Smooth talker: " + ", ".join(bluffers) +
            f" ({best_fools} player{'s' if best_fools != 1 else ''} fooled)"
        )
    with st.expander("Every clue, round by round"):
        for r, tier in enumerate(ge.ROUND_TIERS):
            st.markdown(f"**Round {r + 1} ({tier})**")
            rows = []
            for p in g.players:
                if p in g.bluffed[r]:
                    rows.append({"Player": p, "Clue they said": g.fakes[r][p].text, "Was": "bluff"})
                else:
                    rows.append({"Player": p, "Clue they said": g.clues[r][p].text, "Was": "true"})
            st.dataframe(rows, hide_index=True, use_container_width=True)
    if st.button("Play again with the same players", type="primary", use_container_width=True):
        start_game(g.players, g.high)
    if st.button("New players", use_container_width=True):
        goto("setup")


SCREENS = {
    "setup": screen_setup,
    "clue_handoff": screen_clue_handoff,
    "clue_view": screen_clue_view,
    "speak": screen_speak,
    "point": screen_point,
    "reveal": screen_reveal,
    "final_handoff": screen_final_handoff,
    "final_pick": screen_final_pick,
    "results": screen_results,
}

if not tracking.current_user():
    screen_login()
else:
    if "stage" not in S:
        S.stage = "setup"
    with st.sidebar:
        st.caption(f"Playing as {tracking.current_user()}")
        with st.expander("Quick rules"):
            st.write("Keep your clue card private, but read its text aloud. You may bluff once.")
            st.write("Trust an honest clue: both players get +1. Trust a bluff: the bluffer gets +2.")
            st.write("Final guess: exact +5, within 5 +3, within 10 +1.")
        if S.stage != "setup" and st.button("End game"):
            goto("setup")
        if st.button("Change username"):
            tracking.sign_out()
            st.rerun()
    SCREENS[S.stage]()
