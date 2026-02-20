# Prosecutor Email Draft Template

After completing the legal analysis, generate a draft email to the prosecutor with these characteristics:

## Format: SUBSTANCE ONLY

**CRITICAL**: Generate ONLY the issue paragraphs. No greeting, no subject line, no intro ("I've reviewed..."), no closing ("Let me know..."), no signature.

The user will add their own context when sending. You provide just the legal substance.

## Content Guidelines

### What to Include
- **1-2 strongest issues** only (not exhaustive list)
- Focus on issues that create real suppression risk or trial problems
- Mention specific legal standards (State v. Prado, WAC 448-14, etc.)
- Frame issues as potential problems for the State's case

### Tone & Style
- **Professional but conversational** - not overly formal or stiff
- **Respectful** - acknowledge prosecutor's position
- **Strategic** - highlight strongest issues without revealing full strategy
- **Confident but not aggressive** - show strength without antagonizing

### What NOT to Include
- ❌ Subject line, greeting, or signature
- ❌ Intro phrases ("I've reviewed the discovery", "Wanted to touch base")
- ❌ Closing phrases ("Let me know", "Happy to discuss", "Thanks")
- ❌ Full legal analysis or motion preview
- ❌ Detailed case law discussion
- ❌ All issues found (save for motions)
- ❌ Anything that boxes you into a position
- ❌ Threats or ultimatums
- ❌ Demands (only suggestions)

## Example Outputs (SUBSTANCE ONLY)

### Strong Suppression Case

```
The reasonable suspicion for the stop looks pretty thin under State v. Prado. The report notes "weaving within lane" as the sole basis, but there's only one instance documented with no other concerning factors. That's going to be a tough sell for RS.

The observation period on the breath test appears to clock in at 14 minutes based on the times documented. WAC 448-14 requires 15, so we'd be looking at a suppression issue there as well.
```

### Moderate Issues Case

```
The breath test compliance documentation is a bit unclear, and I'm seeing some potential WAC 448-14 issues that could complicate things. There's also the question of whether the Miranda advisement was adequate given the circumstances.
```

### Weak State Case / Strong Defense

```
The stop itself has RS problems under Prado - we're talking about minimal weaving with no other factors documented. Beyond that, there are multiple breath test compliance issues (observation period, mouth alcohol check, operator certification) that are going to make getting that result in very difficult.

Without the breath test, you're looking at an impairment-only case with pretty limited observations. I think that's going to be a tough road at trial.
```

### Minor Issues / More Negotiation-Focused

```
While the State's case has some strength, there are a few areas where I think we could run into problems - mainly around the FST administration and some timeline gaps in the report.

AFF is interested in resolving this efficiently if there's a reasonable path forward. No major priors, good work history, took responsibility early on.
```

## Strategic Considerations

**Lead with strength but don't overplay:**
- If you have one killer issue, lead with that
- If you have multiple moderate issues, pick the strongest 2
- Save the deep dive for actual motion practice

**Frame as prosecutor's problem, not your brilliance:**
- "The report shows..." not "I discovered..."
- "This creates an issue for the State" not "I'm going to win on this"
- Focus on the evidence, not your analysis

**Positioning based on case strength:**
- **Strong suppression issues**: State the legal problems directly and confidently
- **Moderate issues**: Note concerns about compliance or procedural issues
- **Weak State case**: Point out multiple problems that compound
- **Negotiation-focused**: Mention client's circumstances and interest in resolution

**What the user will add separately:**
- Subject line with case reference
- Greeting ("Hi [Name]")
- Context ("I've reviewed the discovery", "Wanted to touch base")
- Closing ("Let me know", "Happy to discuss")
- Signature

## Sanitization Notes

When using in MCP analysis:
- Replace all names with initials (AFF, GLZ, etc.)
- Replace case numbers with placeholders ([CASE_NUM_001])
- Use specific initials for defendant in substance paragraphs
- Keep it brief and focused on the legal issues

**Example sanitized output (substance only):**

```
The RS for the stop under Prado looks thin - single lane weaving with no other factors documented.

The breath test observation period is 14 minutes per the report timestamps. WAC 448-14 requires 15, so we're looking at a suppression issue there.
```

User will add their own context:
- Subject line (e.g., "State v. AFF - Discovery Review")
- Greeting (e.g., "Hi [Prosecutor Name]")
- Intro (e.g., "I've reviewed the discovery in the AFF case")
- Closing (e.g., "Let me know if you want to discuss")
- Signature (e.g., "Thanks, Tony")

This keeps the generated content focused purely on legal substance, giving the user full control over tone and framing.
