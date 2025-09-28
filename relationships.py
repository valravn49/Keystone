import os
import matplotlib
matplotlib.use("Agg")  # ✅ Use a headless backend for servers/containers
import matplotlib.pyplot as plt
import networkx as nx
from datetime import datetime

def plot_relationships(state, save_dir="logs/relationships"):
    """Generate and save a visual map of sibling relationships."""
    rels = state.get("relationships", {})
    if not rels:
        return None

    os.makedirs(save_dir, exist_ok=True)

    G = nx.DiGraph()
    for key, vals in rels.items():
        a, b = key.split("→")
        affection = vals.get("affection", 0.0)
        teasing = vals.get("teasing", 0.0)
        conflict = vals.get("conflict", 0.0)

        if affection > 0.05:
            G.add_edge(a, b, weight=affection, color="green", style="solid")
        if teasing > 0.05:
            G.add_edge(a, b, weight=teasing, color="purple", style="dashed")
        if conflict > 0.05:
            G.add_edge(a, b, weight=conflict, color="red", style="dotted")

    pos = nx.circular_layout(G)  # nice symmetric layout
    edges = G.edges()

    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_size=2000, node_color="lightblue")
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold")

    # Draw edges with attributes
    for edge in edges:
        color = G.edges[edge]["color"]
        style = G.edges[edge]["style"]
        weight = G.edges[edge]["weight"] * 5  # scale thickness
        nx.draw_networkx_edges(
            G, pos,
            edgelist=[edge],
            edge_color=color,
            style=style,
            width=weight,
            arrows=True
        )

    filename = os.path.join(save_dir, f"relationships_{datetime.now().date()}.png")
    plt.title("Sibling Relationship Map")
    plt.axis("off")
    plt.savefig(filename)
    plt.close()

    return filename
