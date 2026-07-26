"""Deterministic support layer for the LLM build advisor.

The split of labour is deliberate and load-bearing: the model is the strategic
reasoner, and everything in this package is the part that must not be left to a
model -- deriving facts from our data, enforcing legality, and repairing invalid
output. Nothing here simulates combat or scores a build. If a module in here
starts deciding which build is *best*, it is in the wrong package.
"""
