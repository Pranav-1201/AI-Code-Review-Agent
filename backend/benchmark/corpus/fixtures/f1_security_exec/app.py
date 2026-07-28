"""Fixture: Dangerous Function (eval/exec/compile). TPs + safe decoys."""


def run_user_code(payload):
    return eval(payload)                    # TP dangerous_function


def run_source(src):
    exec(src)                               # TP dangerous_function


def build_and_eval(expr):
    code = compile(expr, "<s>", "eval")     # TP dangerous_function (compile)
    return eval(code)                       # TP dangerous_function


def documentation():
    msg = "call eval() carefully here"      # decoy: eval in a string literal
    # never run exec() on user input        <- decoy: exec in a comment
    return msg
