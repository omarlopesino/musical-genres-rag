"""What flattens the top of every ranking.

At sixty the first place and the fifth are worth almost the same, so what the rankings agree on
decides the order rather than how sure any one of them was about its own best hit.
"""
FUSION_CONSTANT = 60

"""Fuses rankings that have no score in common.

Every ranking votes 1 / (constant + rank) for what it found, and the votes are added, so what all of
them returned rises over what only one of them put first. No score is ever read: a bm25 score and a
cosine distance are not the same kind of number and cannot be added, and the rank is the one thing
both of them do say.
"""
class ReciprocalRankFusion:

    def __init__(self, constant = FUSION_CONSTANT):
        self.constant = constant

    """The ids of every ranking, best first, cut to the limit asked for.

    Takes as many rankings as there are, rather than the two a hybrid search has, so a third way of
    searching costs no change here. Ties break on the best rank any ranking gave an id and then on
    the id itself, so the same rankings always fuse into the same order however they were passed.
    """
    def fuse(self, rankings, limit = None):
        scores = {}
        best = {}
        for ranking in rankings:
            for position, id in enumerate(ranking):
                rank = position + 1
                scores[id] = scores.get(id, 0) + 1 / (self.constant + rank)
                best[id] = min(best.get(id, rank), rank)

        fused = sorted(scores, key = lambda id: (-scores[id], best[id], id))

        return fused if limit is None else fused[:limit]
