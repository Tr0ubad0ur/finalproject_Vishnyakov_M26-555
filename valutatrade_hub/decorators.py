import functools
import inspect
from collections.abc import Callable

from valutatrade_hub.logging_config import setup_logging


def _fmt(value: object) -> str:
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _context(params: dict) -> str:
    """Кто и с чем работает: user, currency, amount (пароль не логируется)."""
    parts = [f"user={params.get('username', params.get('user_id'))!r}"]
    if "currency_code" in params:
        parts.append(f"currency={params['currency_code']!r}")
    if "amount" in params:
        parts.append(f"amount={_fmt(params['amount'])}")
    return " ".join(parts)


def _rate_fields(result: object) -> str:
    if isinstance(result, dict) and "rate" in result:
        return f" rate={result['rate']:.2f} base={result.get('base')!r}"
    return ""


def _verbose_fields(result: object) -> str:
    if isinstance(result, dict) and "before" in result:
        return f" wallet={result['before']:.4f}->{result['after']:.4f}"
    return ""


def log_action(action: str, verbose: bool = False) -> Callable:
    """Логирует операцию на уровне INFO; исключения пробрасывает дальше."""

    def decorator(func: Callable) -> Callable:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = setup_logging("actions")
            context = _context(signature.bind(*args, **kwargs).arguments)
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                logger.info(
                    "%s %s result=ERROR error_type=%s error_message=%r",
                    action,
                    context,
                    type(exc).__name__,
                    str(exc),
                )
                raise
            extra = _verbose_fields(result) if verbose else ""
            logger.info(
                "%s %s%s result=OK%s", action, context, _rate_fields(result), extra
            )
            return result

        return wrapper

    return decorator
