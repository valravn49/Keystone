import os
import matplotlib.pyplot as plt
import networkx as nx
from datetime import datetime

# ---------------- Relationship Adjustments ----------------
def adjust_relationship(state, a: str, b: str, affection=0.0, teasing=0.0, conflict=0.0):
    """
    Incrementally adjust relationship values between siblings.
    Values are clamped between 0.0 and 1.0.
    """
    key = f"{a}→{b}"
    rels = state.setdefault("relationships", {})
    rel = rels.setdefault(key, {"affection": 0.5, "teasing": 0.5, "conflict": 0.5})

    rel["affection"] = max(0.0, min(1.0, rel["affection"] + affection))
    rel["teasing"]   = max(0.0, min(1.0, rel["teasing"] + teasing))
    rel["conflict"]  = max(0.0, min(1.0, rel["conflict"] + conflict))

    rels[key] = rel


# ---------------- Relationship Evolution ----------------
def evolve_relationships(state):
    """
    Natural daily drift — relationships shift slowly over time.
    Keeps things from being static forever.
    """
    rels = state.get("relationships", {})
    for rel in rels.values():
        # Gentle regression toward neutral (0.5)
        for k in ["affection", "teasing", "conflict"]:
            if rel[k] > 0.5:
                rel[k] -= 0.01
            elif rel[k] < 0.5:
                rel[k] += 0.01
            rel[k] = max(0.0, min(1.0, rel[k]))


# ---------------- Relationship Visualization ----------------
def plot_relationships(state, save_dir="logs/relationships"):
    """
    Generate and save a visual map of sibling relationships.
    Green = affection, purple dashed = teasing, red dotted = conflict.
    """
    rels = state.get("relationships", {})
    if not rels:
        return None

    os.makedirs(save_dir, exist_ok=True)

    G = nx.DiGraph()
    for key, vals in rels.items():
        a, b = key.split("→")
        affection = vals.get("affection", 0.0)
        teasing   = vals.get("teasing", 0.0)
        conflict  = vals.get("conflict", 0.0)

        if affection > 0.05:
            G.add_edge(a, b, weight=affection, color="green", style="solid")
        if teasing > 0.05:
            G.add_edge(a, b, weight=teasing, color="purple", style="dashed")
        if conflict > 0.05:
            G.add_edge(a, b, weight=conflict, color="red", style="dotted")

    pos = nx.circular_layout(G)  # consistent layout
    edges = G.edges()

    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_size=2000, node_color="lightblue")
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold")

    # Draw edges with attributes
    for edge in edges:
        color = G.edges[edge]["color"]
        style = G.edges[edge]["style"]
        weight = G.edges[edge]["weight"] * 5  # scale line thickness
        nx.draw_networkx_edges(
            G, pos,
            edgelist=[edge],
            edge_color=color,
            style=style,
            width=weight,
            arrows=True,
            arrowsize=20
        )

    filename = os.path.join(save_dir, f"relationships_{datetime.now().date()}.png")
    plt.title("Sibling Relationship Map")
    plt.axis("off")
    plt.savefig(filename)
    plt.close()

    return filename
