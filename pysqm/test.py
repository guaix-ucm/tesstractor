import re


a = "r, 06.23m,0000299932Hz,0000000000c,0000000.000s, 020.9C\n"

p = re.compile(r"""
                \s* # Skip whitespace
                (?P<cmd>[rim]) # Command
                ,\s*
                (?P<muind>\d*.\d*)m
                ,\s*
                (?P<muind1>\d*)Hz
                ,\s*
                (?P<muind2>\d*)c
                ,\s*
                (?P<muind3>\d*.\d*)s
                ,\s*
                (?P<muind4>\d*.\d*)C
                """
               , re.VERBOSE)

print p

m = p.match(a)

if m:
    print m.group()
    print m.groups()