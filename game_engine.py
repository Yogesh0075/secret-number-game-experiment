"""Rules engine for "The Secret Number".

Pure Python: no UI, no network, no AI. Every clue is a small template with a
true/false test, so correctness never depends on a language model.

Game in one line: one secret number, three rounds of private clues (easy ->
medium -> hard), a spoken sentence per player, a trust vote (bluffs pay if
they fool people), and a final multiple-choice guess where closer picks score more.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

ROUNDS = 3
ROUND_TIERS = ("easy", "medium", "hard")
# Share of the range that must still be possible after each round. Keeps big
# groups from solving the number in round 1 just because 15 clues were dealt.
ROUND_FLOOR_FRACTIONS = (0.15, 0.05, 0.02)
BLUFFS_PER_PLAYER = 1
# Trust-choice scoring. Trusting an honest player pays both of you; a bluff
# pays the bluffer double for every player it fools, but a flop costs a point.
TRUST_POINTS = 1      # to an honest player for each player who trusted them
GOOD_READ_POINTS = 1  # to a player who trusted an honest player
FOOLED_POINTS = 2     # to a bluffer for each player who trusted them
FLOP_PENALTY = 1      # a bluffer nobody trusted loses this
OPTION_COUNT = 5
MIN_PLAYERS, MAX_PLAYERS = 2, 20


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def bluff_cap(n_players: int) -> int:
    """Most players allowed to bluff in the same round."""
    return max(1, (n_players + 1) // 3)


def points_for_guess(secret: int, guess: int) -> int:
    d = abs(secret - guess)
    if d == 0:
        return 5
    if d <= 5:
        return 3
    if d <= 10:
        return 1
    return 0


def digit_sum(k: int) -> int:
    return sum(int(c) for c in str(k))


def digit_product(k: int) -> int:
    product = 1
    for c in str(k):
        product *= int(c)
    return product


def has_digit(k: int, digit: int) -> bool:
    return str(digit) in str(k)


def is_palindrome(k: int) -> bool:
    text = str(k)
    return text == text[::-1]


def is_prime(k: int) -> bool:
    if k < 2:
        return False
    for i in range(2, math.isqrt(k) + 1):
        if k % i == 0:
            return False
    return True


def _clamp(v: int, a: int, b: int) -> int:
    return max(a, min(b, v))


# --------------------------------------------------------------------------
# Clue templates. Each returns (text, predicate). Parameters are sampled near
# the secret so clues are useful; make_clue() then keeps only the ones whose
# truth value for the secret is what we asked for (true clue or fake clue).
# --------------------------------------------------------------------------
def _under(rng, lo, hi, n):
    x = _clamp(n + rng.randint(-25, 25), lo + 1, hi + 1)
    return f"This number is less than {x}", lambda k: k < x


def _over(rng, lo, hi, n):
    x = _clamp(n + rng.randint(-25, 25), lo - 1, hi - 1)
    return f"This number is more than {x}", lambda k: k > x


def _parity(rng, lo, hi, n):
    p = rng.choice((0, 1))
    return ("This is an even number" if p == 0 else "This is an odd number"), lambda k: k % 2 == p


def _range_third(rng, lo, hi, n):
    zone = rng.randrange(3)
    size = hi - lo + 1
    start = lo + zone * size // 3
    end = hi if zone == 2 else lo + (zone + 1) * size // 3 - 1
    labels = ("lower", "middle", "upper")
    return (
        f"It is in the {labels[zone]} part of the range, between {start} and {end}",
        lambda k: start <= k <= end,
    )


def _digit_count(rng, lo, hi, n):
    count = rng.choice((1, 2, 3))
    noun = "digit" if count == 1 else "digits"
    return f"This number has {count} {noun}", lambda k: len(str(k)) == count


def _contains_digit(rng, lo, hi, n):
    digit = n % 10 if rng.random() < 0.45 else rng.randint(0, 9)
    return f"The digit {digit} appears in this number", lambda k: has_digit(k, digit)


def _near_multiple(rng, lo, hi, n):
    multiple = rng.choice((5, 10, 15, 20, 25))
    distance = rng.choice((1, 2, 3))
    return (
        f"It is within {distance} of a multiple of {multiple}",
        lambda k: min(k % multiple, multiple - (k % multiple)) <= distance,
    )


def _between(rng, lo, hi, n):
    a = _clamp(n + rng.randint(-15, 10), lo, hi - 5)
    b = _clamp(a + rng.randint(8, 25), a + 5, hi)
    return f"This number is between {a} and {b}", lambda k: a <= k <= b


def _last_digit(rng, lo, hi, n):
    d = n % 10 if rng.random() < 0.5 else rng.randint(0, 9)
    return f"The last digit is {d}", lambda k: k % 10 == d


def _first_digit(rng, lo, hi, n):
    d = _clamp(int(str(n)[0]) + rng.randint(-1, 1), 1, 9)
    return f"The first digit is {d}", lambda k: int(str(k)[0]) == d


def _divisible(rng, lo, hi, n):
    m = rng.choice((2, 3, 4, 5, 6, 7, 9))
    if rng.random() < 0.5:
        return f"It can be divided equally by {m}", lambda k: k % m == 0
    return f"It cannot be divided equally by {m}", lambda k: k % m != 0


def _remainder(rng, lo, hi, n):
    divisor = rng.choice((3, 4, 5, 6, 7, 8, 9))
    remainder = rng.randrange(divisor)
    return (
        f"When divided by {divisor}, {remainder} is left over",
        lambda k: k % divisor == remainder,
    )


def _tens_neighborhood(rng, lo, hi, n):
    center = _clamp((n // 10) * 10 + rng.choice((-10, 0, 10)), lo, hi)
    width = rng.choice((5, 8, 12))
    return (
        f"It is close to {center}: within {width}",
        lambda k: abs(k - center) <= width,
    )


def _digit_sum_eq(rng, lo, hi, n):
    s = max(1, digit_sum(n) + rng.randint(-3, 3))
    return f"Add its digits together: the total is {s}", lambda k: digit_sum(k) == s


def _digit_sum_cmp(rng, lo, hi, n):
    s = max(2, digit_sum(n) + rng.randint(-4, 4))
    if rng.random() < 0.5:
        return f"Adding its digits gives more than {s}", lambda k: digit_sum(k) > s
    return f"Adding its digits gives less than {s}", lambda k: digit_sum(k) < s


def _prime(rng, lo, hi, n):
    if rng.random() < 0.5:
        return "This is a prime number", is_prime
    return "This is not a prime number", lambda k: not is_prime(k)


def _digit_gap(rng, lo, hi, n):
    d = _clamp(abs(n // 10 % 10 - n % 10) + rng.randint(-2, 2), 0, 9)
    return (
        f"The difference between its two digits is {d}",
        lambda k: 10 <= k <= 99 and abs(k // 10 - k % 10) == d,
    )


def _last_vs_first(rng, lo, hi, n):
    if rng.random() < 0.5:
        return (
            "The last digit is bigger than the first digit",
            lambda k: k >= 10 and k % 10 > int(str(k)[0]),
        )
    return (
        "The last digit is smaller than the first digit",
        lambda k: k >= 10 and k % 10 < int(str(k)[0]),
    )


def _digit_product(rng, lo, hi, n):
    product = max(0, digit_product(n) + rng.randint(-8, 8))
    return f"Multiply its digits: you get {product}", lambda k: digit_product(k) == product


def _palindrome(rng, lo, hi, n):
    if rng.random() < 0.5:
        return "It looks the same when read from either side", is_palindrome
    return "It looks different when read from either side", lambda k: not is_palindrome(k)


def _same_or_different_digits(rng, lo, hi, n):
    if rng.random() < 0.5:
        return (
            "The last two digits are the same",
            lambda k: k >= 10 and str(k)[-1] == str(k)[-2],
        )
    return (
        "The last two digits are different",
        lambda k: k >= 10 and str(k)[-1] != str(k)[-2],
    )


def _square_neighbor(rng, lo, hi, n):
    square = rng.choice(tuple(x * x for x in range(1, math.isqrt(hi) + 1)))
    distance = rng.choice((1, 2, 3, 4))
    return (
        f"It is within {distance} of {square}, which is a square number",
        lambda k: abs(k - square) <= distance,
    )


TEMPLATES = {
    "easy": (
        _under, _over, _parity, _range_third, _digit_count, _contains_digit,
        _near_multiple,
    ),
    "medium": (
        _between, _last_digit, _first_digit, _divisible, _remainder,
        _tens_neighborhood,
    ),
    "hard": (
        _digit_sum_eq, _digit_sum_cmp, _prime, _digit_gap, _last_vs_first,
        _digit_product, _palindrome, _same_or_different_digits, _square_neighbor,
    ),
}


@dataclass(frozen=True)
class Clue:
    text: str
    tier: str
    is_true: bool
    matches: frozenset  # every number in the range for which the clue holds


def make_clue(secret, tier, want_true, rng, lo, hi, avoid=()):
    """Return a Clue that is true (or false) for `secret`, or None if unlucky."""
    total = hi - lo + 1
    templates = TEMPLATES[tier]
    for _ in range(300):
        text, pred = rng.choice(templates)(rng, lo, hi, secret)
        if text in avoid or bool(pred(secret)) != want_true:
            continue
        matches = frozenset(k for k in range(lo, hi + 1) if pred(k))
        if not matches or len(matches) == total:  # empty or says nothing
            continue
        return Clue(text, tier, want_true, matches)
    return None


def _deal_round(secret, n_players, tier, possible, floor, rng, lo, hi, seen_texts):
    """Deal fresh true clues while keeping at least `floor` candidates if possible."""
    cur = set(possible)
    clues, used = [], set(seen_texts)
    for _ in range(n_players):
        chosen = None
        for _attempt in range(60):
            c = make_clue(secret, tier, True, rng, lo, hi, avoid=used)
            if c is None:
                break
            new = cur & c.matches
            if floor <= len(new) < len(cur):
                chosen = c
                break
        if chosen is None:
            # An unusual combination of clues may leave no fresh clue that
            # meets the floor. Still prefer a new card and lose as little of
            # the candidate pool as possible rather than repeat earlier text.
            best, best_possible = None, set()
            for _attempt in range(300):
                c = make_clue(secret, tier, True, rng, lo, hi, avoid=used)
                if c is None:
                    break
                new = cur & c.matches
                if len(new) > len(best_possible):
                    best, best_possible = c, new
            if best is None:
                raise RuntimeError("could not create a fresh clue")
            chosen = best
        clues.append(chosen)
        used.add(chosen.text)
        cur &= chosen.matches
    return clues, frozenset(cur)


def build_options(secret, possible, lo, hi, rng, n=OPTION_COUNT):
    """Real number + 2 plausible decoys + far-away fillers, sorted ascending."""
    n = min(n, hi - lo + 1)
    opts = {secret}
    near = [x for x in possible if x != secret]
    rng.shuffle(near)
    for x in near[:2]:
        opts.add(x)
    mid = [x for x in range(lo, hi + 1) if 1 <= abs(x - secret) <= 9 and x not in opts]
    rng.shuffle(mid)
    while len(opts) < 3 and mid:
        opts.add(mid.pop())
    far = [x for x in range(lo, hi + 1) if abs(x - secret) > 10 and x not in opts]
    rng.shuffle(far)
    while len(opts) < n and far:
        opts.add(far.pop())
    rest = [x for x in range(lo, hi + 1) if x not in opts]
    rng.shuffle(rest)
    while len(opts) < n and rest:
        opts.add(rest.pop())
    return sorted(opts)


# --------------------------------------------------------------------------
# Game state
# --------------------------------------------------------------------------
@dataclass
class Game:
    players: list
    secret: int
    low: int
    high: int
    clues: list          # per round: {player: true Clue}
    fakes: list          # per round: {player: false Clue}, used only on bluff
    possible_after: list  # per round: frozenset of numbers still possible
    speak_orders: list   # per round: shuffled list of players
    options: list
    bluffs_left: dict = field(default_factory=dict)
    bluffed: list = field(default_factory=list)       # per round: set of players
    votes: list = field(default_factory=list)         # per round: {player: trusted player | None}
    fingers: list = field(default_factory=list)       # per round: {player: times trusted}
    round_points: list = field(default_factory=list)  # per round: {player: int}
    picks: dict = field(default_factory=dict)

    # ----- bluffing -----
    def can_bluff(self, r: int, player: str) -> bool:
        return (
            self.bluffs_left[player] > 0
            and player not in self.bluffed[r]
            and len(self.bluffed[r]) < bluff_cap(len(self.players))
        )

    def bluff_block_reason(self, r: int, player: str) -> str:
        if self.bluffs_left[player] <= 0:
            return "You've already used your bluff."
        if player in self.bluffed[r]:
            return "You're already bluffing this round."
        if len(self.bluffed[r]) >= bluff_cap(len(self.players)):
            return "Too many players are already bluffing this round."
        return ""

    def use_bluff(self, r: int, player: str) -> bool:
        if not self.can_bluff(r, player):
            return False
        self.bluffed[r].add(player)
        self.bluffs_left[player] -= 1
        return True

    def clue_seen(self, r: int, player: str) -> Clue:
        """The clue the player actually gets (the fake one if they bluffed)."""
        if player in self.bluffed[r]:
            return self.fakes[r][player]
        return self.clues[r][player]

    # ----- trust vote scoring -----
    def score_round(self, r: int, votes: dict) -> dict:
        """Score one round from trust choices ({player: trusted player | None}).

        Honest target: target +1, pointer +1. Bluffing target: bluffer +2 per
        player fooled. A bluffer nobody trusted loses 1. In a two-player game,
        ``None`` means "I think the other player is bluffing."
        """
        if len(self.votes) > r:
            raise ValueError("round already scored")
        if set(votes) != set(self.players):
            raise ValueError("every player must make a trust choice")
        for pointer, target in votes.items():
            if target is None and len(self.players) == 2:
                continue
            if target not in self.players or target == pointer:
                raise ValueError(f"{pointer} must trust another player")
        pts = {p: 0 for p in self.players}
        received = {p: 0 for p in self.players}
        for pointer, target in votes.items():
            if target is None:
                continue
            received[target] += 1
            if target in self.bluffed[r]:
                pts[target] += FOOLED_POINTS
            else:
                pts[target] += TRUST_POINTS
                pts[pointer] += GOOD_READ_POINTS
        for b in self.bluffed[r]:
            if received[b] == 0:
                pts[b] -= FLOP_PENALTY
        self.votes.append(dict(votes))
        self.fingers.append(received)
        self.round_points.append(pts)
        return pts

    # ----- final guess -----
    def submit_pick(self, player: str, value: int) -> None:
        if value not in self.options:
            raise ValueError("not one of the options")
        self.picks[player] = value

    def trust_points(self) -> dict:
        return {p: sum(rp[p] for rp in self.round_points) for p in self.players}

    def good_reads(self) -> dict:
        """How often each player trusted an honest clue."""
        reads = {p: 0 for p in self.players}
        for r, round_votes in enumerate(self.votes):
            for player, target in round_votes.items():
                if target is not None and target not in self.bluffed[r]:
                    reads[player] += 1
        return reads

    def bluff_fools(self) -> dict:
        """How many opponents trusted each player's bluff across the game."""
        fooled = {p: 0 for p in self.players}
        for r, bluffers in enumerate(self.bluffed):
            for player in bluffers:
                fooled[player] += self.fingers[r][player] if len(self.fingers) > r else 0
        return fooled

    def guess_points(self) -> dict:
        return {p: points_for_guess(self.secret, self.picks[p]) for p in self.picks}

    def totals(self) -> dict:
        trust, guess = self.trust_points(), self.guess_points()
        return {p: trust[p] + guess.get(p, 0) for p in self.players}

    def leaderboard(self) -> list:
        t = self.totals()
        return sorted(t.items(), key=lambda kv: (-kv[1], kv[0]))

    def winners(self) -> list:
        t = self.totals()
        best = max(t.values())
        return [p for p, v in t.items() if v == best]


def new_game(players, seed=None, lo=1, hi=100) -> Game:
    players = [p.strip() for p in players]
    if not MIN_PLAYERS <= len(players) <= MAX_PLAYERS:
        raise ValueError(f"need {MIN_PLAYERS}-{MAX_PLAYERS} players")
    if any(not p for p in players) or len(set(players)) != len(players):
        raise ValueError("player names must be non-empty and unique")
    if hi - lo < 20:
        raise ValueError("range too small")

    rng = random.Random(seed)
    secret = rng.randint(lo, hi)
    size = hi - lo + 1
    floors = [max(2, round(size * f)) for f in ROUND_FLOOR_FRACTIONS]

    possible = frozenset(range(lo, hi + 1))
    clues, fakes, possible_after, speak_orders = [], [], [], []
    seen_texts = set()
    for r, tier in enumerate(ROUND_TIERS):
        dealt, possible = _deal_round(
            secret, len(players), tier, possible, floors[r], rng, lo, hi, seen_texts
        )
        seen_texts.update(c.text for c in dealt)
        order = players[:]
        rng.shuffle(order)  # so the first-listed player isn't always first
        clues.append(dict(zip(order, dealt)))

        taken = set(seen_texts)
        fake_map = {}
        for p in players:
            f = make_clue(secret, tier, False, rng, lo, hi, avoid=taken)
            for alt in (t for t in ROUND_TIERS if f is None):
                f = make_clue(secret, alt, False, rng, lo, hi, avoid=taken)
            if f is None:
                raise RuntimeError("could not create a fresh bluff clue")
            fake_map[p] = f
            taken.add(f.text)
        fakes.append(fake_map)
        seen_texts.update(f.text for f in fake_map.values())
        possible_after.append(possible)
        speak = players[:]
        rng.shuffle(speak)
        speak_orders.append(speak)

    return Game(
        players=players,
        secret=secret,
        low=lo,
        high=hi,
        clues=clues,
        fakes=fakes,
        possible_after=possible_after,
        speak_orders=speak_orders,
        options=build_options(secret, possible, lo, hi, rng),
        bluffs_left={p: BLUFFS_PER_PLAYER for p in players},
        bluffed=[set() for _ in ROUND_TIERS],
    )
