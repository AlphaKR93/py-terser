from ._suite import SuiteTransformer, TransformerFlag


class Contracts(SuiteTransformer):
    FLAGS = TransformerFlag.REQUIRES_IMPORT_RESOLVE


