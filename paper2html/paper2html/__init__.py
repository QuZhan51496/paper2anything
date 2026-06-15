"""Paper2HTML - Convert academic papers (PDF) to beautiful HTML pages."""

def paper2html(*args, **kwargs):
    from paper2html.pipeline import paper2html as _paper2html

    return _paper2html(*args, **kwargs)

def build_agent_page(*args, **kwargs):
    from paper2html.agent import build_agent_page as _build_agent_page

    return _build_agent_page(*args, **kwargs)

__all__ = ["paper2html", "build_agent_page"]
