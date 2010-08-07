"""Module with functions operating on IndexedBase, Indexed and Idx objects

    - Check shape conformance
    - Determine indices in resulting expression

    etc.
"""

from sympy.tensor.indexed import Idx, IndexedBase, Indexed
from sympy.utilities import all


class IndexConformanceException(Exception):
    pass

def _remove_repeated(inds):
    """Removes repeated objects from sequences

    Returns a set of the unique objects and a tuple of all that have been
    removed.

    >>> from sympy.tensor.index_methods import _remove_repeated
    >>> l1 = [1, 2, 3, 2]
    >>> _remove_repeated(l1)
    (set([1, 3]), (2,))

    """
    sum_index = {}
    for i in inds:
        if i in sum_index:
            sum_index[i] += 1
            assert sum_index[i] == 1, "Index %s repeated more than twice" % i
        else:
            sum_index[i] = 0
    inds = filter(lambda x: not sum_index[x], inds)
    return set(inds), tuple([ i for i in sum_index if sum_index[i] ])

def _get_indices_Mul(expr, return_dummies=False):
    """Determine the outer indices of a Mul object.

    >>> from sympy.tensor.index_methods import _get_indices_Mul
    >>> from sympy.tensor.indexed import IndexedBase, Idx
    >>> i, j, k = map(Idx, ['i', 'j', 'k'])
    >>> x = IndexedBase('x')
    >>> y = IndexedBase('y')
    >>> _get_indices_Mul(x[i, k]*y[j, k])
    (set([i, j]), {})
    >>> _get_indices_Mul(x[i, k]*y[j, k], return_dummies=True)
    (set([i, j]), {}, (k,))

    """

    junk, factors = expr.as_coeff_terms()
    inds = map(get_indices, factors)
    inds, syms = zip(*inds)

    inds = map(list, inds)
    inds = reduce(lambda x, y: x + y, inds)
    inds, dummies = _remove_repeated(inds)

    symmetry = {}
    for s in syms:
        for pair in s:
            if pair in symmetry:
                symmetry[pair] *= s[pair]
            else:
                symmetry[pair] = s[pair]

    if return_dummies:
        return inds, symmetry, dummies
    else:
        return inds, symmetry


def _get_indices_Add(expr):
    """Determine outer indices of an Add object.

    In a sum, each term must have the same set of outer indices.  A valid
    expression could be

        x(i)*y(j) - x(j)*y(i)

    But we do not allow expressions like:

        x(i)*y(j) - z(j)*z(j)

    FIXME: Add support for Numpy broadcasting

    >>> from sympy.tensor.index_methods import _get_indices_Add
    >>> from sympy.tensor.indexed import IndexedBase, Idx
    >>> i, j, k = map(Idx, ['i', 'j', 'k'])
    >>> x = IndexedBase('x')
    >>> y = IndexedBase('y')
    >>> _get_indices_Add(x[i] + x[k]*y[i, k])
    (set([i]), {})

    """

    inds = map(get_indices, expr.args)
    inds, syms = zip(*inds)

    # allow broadcast of scalars
    non_scalars = filter(lambda x: x != set(), inds)
    if not non_scalars:
        return set(), {}

    if not all(map(lambda x: x == non_scalars[0], non_scalars[1:])):
        raise IndexConformanceException("Indices are not consistent: %s"%expr)
    if not reduce(lambda x, y: x!=y or y, syms):
        symmetries = syms[0]
    else:
        # FIXME: search for symmetries
        symmetries = {}

    return non_scalars[0], symmetries

def get_indices(expr):
    """Determine the outer indices of expression `expr'

    By `outer' we mean indices that are not summation indices.  Returns a set
    and a dict.  The set contains outer indices and the dict contains
    information about index symmetries.

    Examples
    ========

    >>> from sympy.tensor.index_methods import get_indices
    >>> from sympy import symbols
    >>> from sympy.tensor import IndexedBase, Idx
    >>> x, y, A = map(IndexedBase, ['x', 'y', 'A'])
    >>> i, j, a, z = symbols('i j a z', integer=True)

    The indices of the total expression is determined, Repeated indices imply a
    summation, for instance the trace of a matrix A:

    >>> get_indices(A[i, i])
    (set(), {})

    In the case of many terms, the terms are required to have identical
    outer indices.  Else an IndexConformanceException is raised.

    >>> get_indices(x[i] + A[i, j]*y[j])
    (set([i]), {})

    The concept of `outer' indices applies recursively, starting on the deepest
    level.  This implies that dummies inside parenthesis are assumed to be
    summed first, so that the following expression is handled gracefully:

    >>> get_indices((x[i] + A[i, j]*y[j])*x[j])
    (set([i, j]), {})

    The algorithm also searches for index symmetries, so that

    FIXME: not implemented yet

     >> get_indices(x[i]*y[j] + x[j]*y[i])
    (set([i, j]), {(i, j): 1})
     >> get_indices(x[i]*y[j] - x[j]*y[i])
    (set([i, j]), {(i, j): -1})

    Exceptions
    ==========

    An IndexConformanceException means that the terms ar not compatible, e.g.

    >>> get_indices(x[i] + y[j])                #doctest: +SKIP
            (...)
    IndexConformanceException: Indices are not consistent: x(i) + y(j)


    """
    # We call ourself recursively to determine indices of sub expressions.

    # break recursion
    if isinstance(expr, Indexed):
        c = expr.indices
        inds, dummies = _remove_repeated(c)
        return inds, {}
    elif expr is None:
        return set(), {}
    elif expr.is_Atom:
        return set(), {}

    # recurse via specialized functions
    else:
        if expr.is_Mul:
            return _get_indices_Mul(expr)
        elif expr.is_Add:
            return _get_indices_Add(expr)

        # this test is expensive, so it should be at the end
        elif not expr.has(Indexed):
            return set(), {}
        else:
            raise NotImplementedError(
                    "FIXME: No specialized handling of type %s"%type(expr))

def get_contraction_structure(expr):
    """Determine dummy indices of expression `expr' and describe structure of the expression

    By `dummy' we mean indices that are summation indices.

    The stucture of the expression is determined and returned as follows:

    1) The terms of a conforming summation are returned as a dict where the keys
    are summation indices and the values are terms for which the dummies are
    relevant.

    2) If there are nested Add objects, we recurse to determine summation
    indices for the the deeper terms. The resulting dict is returned as a value
    in the dictionary, and the Add expression is the corresponding key.

    Examples
    ========

    >>> from sympy.tensor.index_methods import get_contraction_structure
    >>> from sympy import symbols
    >>> from sympy.tensor import IndexedBase, Idx
    >>> x, y, A = map(IndexedBase, ['x', 'y', 'A'])
    >>> i, j, k, l = symbols('i j k l', integer=True)
    >>> get_contraction_structure(x[i]*y[i] + A[j, j])
    {(i,): set([x[i]*y[i]]), (j,): set([A[j, j]])}
    >>> get_contraction_structure(x[i]*y[j])
    {None: set([x[i]*y[j]])}

    A nested Add object is returned as a nested dictionary.  The term
    containing the parenthesis is used as the key, and it stores the dictionary
    resulting from a recursive call on the Add expression.

    >>> d = get_contraction_structure(x[i]*(y[i] + A[i, j]*x[j]))
    >>> sorted(d.keys())
    [(i,), x[i]*(A[i, j]*x[j] + y[i])]
    >>> d[(Idx(i),)]
    set([x[i]*(A[i, j]*x[j] + y[i])])
    >>> d[x[i]*(A[i, j]*x[j] + y[i])]
    [{None: set([y[i]]), (j,): set([A[i, j]*x[j]])}]

    Note that the presence of expressions among the dictinary keys indicates a
    factorization of the array contraction.  The summation in the deepest
    nested level must be calculated first so that the external contraction can access
    the resulting array with index j.

    """

    # We call ourself recursively to inspect sub expressions.

    if isinstance(expr, Indexed):
        junk, key = _remove_repeated(expr.indices)
        return {key or None: set([expr])}
    elif expr.is_Atom:
        return {None: set([expr])}
    elif expr.is_Mul:
        junk, junk, key = _get_indices_Mul(expr, return_dummies=True)
        result = {key or None: set([expr])}
        # recurse if we have any Add objects
        addfactors = filter(lambda x: x.is_Add, expr.args)
        if addfactors:
            result[expr] = []
            for factor in addfactors:
                d = get_contraction_structure(factor)
                result[expr].append(d)
        return result
    elif expr.is_Add:
        # Note: we just collect all terms with identical summation indices, We
        # do nothing to identify equivalent terms here, as this would require
        # substitutions or pattern matching in expressions of unknown
        # complexity.
        result = {}
        for term in expr.args:
            # recurse on every term
            d = get_contraction_structure(term)
            for key in d:
                if key in result:
                    result[key] |= d[key]
                else:
                    result[key] = d[key]
        return result

    # this test is expensive, so it should be at the end
    elif not expr.has(Indexed):
        return {None: set([expr])}
    else:
        raise NotImplementedError(
                "FIXME: No specialized handling of type %s"%type(expr))
