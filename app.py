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
    st.caption(f"Round {r + 1} of {ge.ROUNDS} · {ge.ROUND_TIERS[r]} clues")


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
        "One secret number. Everyone gets private clues, says something about "
        "theirs, and can bluff once. Vote on who to trust, then guess the number."
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
        st.write("Bluff on. Say this as if it were true. Nobody else knows.")
        if st.button("Hide and pass the phone", type="primary", use_container_width=True):
            next_after_clue()
        return
    if st.button("Got it. Hide and pass", type="primary", use_container_width=True):
        next_after_clue()
    can = g.can_bluff(r, p)
    if st.button(
        f"Use my bluff ({g.bluffs_left[p]} left)", disabled=not can, use_container_width=True
    ):
        g.use_bluff(r, p)
        S.bluffing = True
        st.rerun()
    if not can:
        st.caption(g.bluff_block_reason(r, p))
    else:
        st.caption("A bluff swaps in a false clue. You get one per game.")


# ------------------------------------------------------------ talk/vote ----
def screen_speak():
    g, r = S.game, S.round
    round_caption()
    st.header("Say it")
    st.write(
        "In this order, each player says one sentence about their clue in their "
        "own words. No exact numbers. Honest or bluffing, your call."
    )
    for i, name in enumerate(g.speak_orders[r], 1):
        st.write(f"{i}. {name}")
    if st.button("Everyone has spoken", type="primary", use_container_width=True):
        goto("point")


def screen_point():
    g, r = S.game, S.round
    round_caption()
    st.header("Point!")
    st.write(
        "On 3, 2, 1, everyone points at the one other player they trust most. "
        "Then record who each player pointed at."
    )
    st.caption(
        "Pointing at an honest player pays you both. A bluff pays its owner double "
        "for every player it fools, but costs a point if nobody falls for it."
    )
    with st.form(f"point_{S.gid}_{r}"):
        picks = {
            p: st.selectbox(
                f"{p} pointed at",
                [q for q in g.players if q != p],
                index=None,
                placeholder="Choose a player",
                key=f"pt_{S.gid}_{r}_{p}",
            )
            for p in g.players
        }
        go = st.form_submit_button("Reveal", type="primary", use_container_width=True)
    if go:
        if any(v is None for v in picks.values()):
            st.error("Choose who every player pointed at.")
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
                "Pointed at": g.votes[r][p],
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
    st.write("Which number is it? Closer picks score more.")
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
        if S.stage != "setup" and st.button("End game"):
            goto("setup")
        if st.button("Change username"):
            tracking.sign_out()
            st.rerun()
    SCREENS[S.stage]()
