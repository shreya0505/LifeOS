"""Trophy definitions — shared between computation and display layers."""

TROPHY_DEFS: list[dict] = [
    {
        "id": "frog_slayer",
        "name": "Frog Slayer",
        "icon": "target",
        "desc": "Eat your most dreaded task — bonus for doing it first",
        "tiers": {
            "bronze": "Frog eaten",
            "silver": "Eaten before noon",
            "gold":   "Eaten as first completed quest",
        },
        "pr_label": "Earliest frog completion",
    },
    {
        "id": "swamp_clearer",
        "name": "Swamp Clearer",
        "icon": "target",
        "desc": "Power through multiple dreaded tasks in one day",
        "tiers": {
            "bronze": "1 frog",
            "silver": "2 frogs",
            "gold":   "4 frogs",
        },
        "pr_label": "Most frogs in a day",
    },
    {
        "id": "forge_master",
        "name": "Forge Master",
        "icon": "flame",
        "desc": "Deep work hours — real focused pomodoros completed",
        "tiers": {
            "bronze": "2 pomos (~1hr)",
            "silver": "6 pomos (~3hr)",
            "gold":   "10 pomos (~5hr)",
        },
        "pr_label": "Most pomos in a day",
    },
    {
        "id": "untouchable",
        "name": "Untouchable",
        "icon": "shield",
        "desc": "Consecutive pomos with zero interruptions",
        "tiers": {
            "bronze": "2 clean streak",
            "silver": "4 clean streak",
            "gold":   "7 clean streak",
        },
        "pr_label": "Longest clean run in a day",
    },
    {
        "id": "quest_closer",
        "name": "Quest Closer",
        "icon": "check-circle",
        "desc": "Close quests — move tasks to done and clear the board",
        "tiers": {
            "bronze": "3 quests",
            "silver": "5 quests",
            "gold":   "8 quests",
        },
        "pr_label": "Most quests closed in a day",
    },
    {
        "id": "scribe",
        "name": "Scribe",
        "icon": "scroll",
        "desc": "Log your intent before and result after every pomo",
        "tiers": {
            "bronze": "1 documented",
            "silver": "3 documented",
            "gold":   "Every pomo today",
        },
        "pr_label": "Best documented count",
    },
    {
        "id": "ironclad",
        "name": "Ironclad",
        "icon": "moon",
        "desc": "Take your breaks — recovery is part of the fight",
        "tiers": {
            "bronze": "1 break taken",
            "silver": "3 breaks taken",
            "gold":   "Every pomo today",
        },
        "pr_label": "Best recovery % in a day",
    },
]
