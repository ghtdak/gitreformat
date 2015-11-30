from __future__ import print_function, division

# def toposort2(data):
#     extras = reduce(set.union, data.itervalues()) - set(data.iterkeys())
#     # Add empty dependences where needed
#     data.update({item: set() for item in extras})
#     while True:
#         ordered = set(item for item, dep in data.iteritems() if not dep)
#         if not ordered:
#             break
#         yield ordered
#         data = {item: (dep - ordered)
#                 for item, dep in data.iteritems()
#                 if item not in ordered}
#     assert not data, "Cyclicitems:\n%s" % '\n'.join(
#             repr(x) for x in data.iteritems())

def ght_ts(data):
    res = []
    ordered = set()
    for item, dep in data.iteritems():
        if not dep:
            ordered.add(item)
    while True:
        if not ordered:
            break
        res.append(ordered)
        data2, ordered2 = {}, set()
        for item, dep in data.iteritems():
            if item not in ordered:
                d = dep - ordered
                data2[item] = d
                if not d:
                    ordered2.add(item)
        data, ordered = data2, ordered2

    return res

def main():
    graph2 = {'A': {'B', 'C'},
              'B': {'D', 'E'},
              'C': {'F'},
              'D': set(),
              'E': {'F'},
              'F': set()}

    for x in ght_ts(graph2):
        print(repr(sorted(x)))

    # print('\n'.join(repr(sorted(x)) for x in toposort2(graph2)))


if __name__ == '__main__':
    main()
