
def get_int(value):
    try:
        return int(value)
    except ValueError:
        return 1