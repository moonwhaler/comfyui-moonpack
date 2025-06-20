class AnyType(str):
  """A special class that is always equal in not equal comparisons. Credit to pythongosssss"""

  def __ne__(self, __value: object) -> bool:
    return False


class FlexibleOptionalInputType(dict):
  """A special class to make flexible nodes that pass data to our python handlers."""

  def __init__(self, type, data: dict | None = None):
    """Initializes the FlexibleOptionalInputType."""
    self.type = type
    self.data = data
    if self.data is not None:
      for k, v in self.data.items():
        self[k] = v

  def __getitem__(self, key):
    if self.data is not None and key in self.data:
      val = self.data[key]
      return val
    return (self.type,)

  def __contains__(self, key):
    """Always contain a key, and we'll always return the tuple above when asked for it."""
    return True


any_type = AnyType("*")
