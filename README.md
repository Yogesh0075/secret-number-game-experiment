# The Secret Number

Pass-and-play party game for 2-15 players on one phone. One secret number,
three rounds of private clues (easy, medium, hard), one spoken sentence each,
a one-time bluff per player, a trust vote by pointing, then a final
multiple-choice guess. Closer guesses score more.

## Scoring

- **Trust choice:** everyone chooses the one other player they trust most.
  Trust an honest player and you both score 1.
- **Two-player trust choice:** each person either trusts the other clue or
  calls it a bluff. Calling a bluff scores no points, but can make a bluff flop.
- **Bluff:** a bluffer scores 2 for every player it fools. If nobody points
  at a bluffer, it loses 1. So bluffing pays when you're convincing.
- **Final guess:** exact 5, within 5 scores 3, within 10 scores 1.
- Bluffs: one per player per game, and at most about a third of the table can
  bluff in the same round.

All clues come from plain Python templates (`game_engine.py`). The clue bank
mixes ranges, digit patterns, multiples and remainders, prime checks,
palindromes, and nearby square numbers. No AI is used for anything that
affects correctness. A clue card's exact text is used only once per game,
including bluff cards.

The landing screen asks for a simple username. It is not a password-protected
account and is stored only for the current browser session.

The app includes a quick rules panel, short round-specific guidance, a
plain-language explanation of each round's score change, and end-game awards
for the sharpest reader and most convincing bluffer.

## Run it locally

    pip install -r requirements.txt
    python test_engine.py        # engine checks + how fast the pool narrows
    streamlit run app.py

## Files

| File | Job |
|------|-----|
| `game_engine.py` | Clue templates, dealing, bluffs, options, scoring |
| `app.py` | Streamlit screens (pass-and-play flow) |
| `tracking.py` | Session-only username helpers |
| `test_engine.py` | Simulates thousands of games and checks the rules |

## Deploy free: Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. On share.streamlit.io, create an app from the repo, main file `app.py`.

## Known limits

- Game state and username live in memory. Refreshing the page ends the game and clears the username.
- Free tiers change and can sleep or pause after inactivity. Check current terms.
- Each Streamlit visitor holds a live session, so ~100 people at the very same
  moment may exceed the free memory. Fine for friends-only testing.
- The secret number sits in server memory; it is never sent to the browser
  until the results screen.
