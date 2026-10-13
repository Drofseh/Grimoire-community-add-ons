# Character importers

Importers read a character built in another tool onto one of the
[character sheets](../character-sheets/) in this repository. They are used from
**Characters → Import a character**, where a dropped file is recognised
automatically. One that only reads uploaded files with YAML can be installed by
any user for their own account from that dialog; one that fetches links or runs
a script is installed by an admin, for everyone, under **Settings → Add-ons**.

| Importer | Reads | Builds on |
| --- | --- | --- |
| [`forge-steel`](forge-steel/forge-steel.yml) | `.ds-hero` files from Forge Steel's Export | [`draw-steel`](../character-sheets/draw-steel/) |
| [`pathbuilder-2e`](pathbuilder-2e/pathbuilder-2e.yml) | Pathbuilder 2e's Export JSON, saved as a file | [`pathfinder-2e`](../character-sheets/pathfinder-2e/) |
| [`dndbeyond`](dndbeyond/dndbeyond.yml) | A publicly shared D&D Beyond character's link, or its JSON (script) | [`dnd-5e-2024`](../character-sheets/dnd-5e-2024/) |
| [`dicecloud-v1`](dicecloud-v1/dicecloud-v1.yml) | A DiceCloud v1 character's link - a private one with your API key - or its API JSON (script) | [`dnd-5e-2024`](../character-sheets/dnd-5e-2024/) |

An importer is a directory named after its `id`, holding `<id>.yml`:

```
importers/
└── my-builder/
    ├── my-builder.yml   # required
    ├── my_builder.py    # only for a script-backed importer
    └── README.md        # optional
```

[**Writing a character importer**](../docs/character-importers.md) covers the
format: recognising files and links, the path language, how each sheet field
type is filled, matching against installed content, and scripts.

Run `python3 scripts/build_index.py` after adding or changing one, and commit
the regenerated `index.json` with it.
