"""Blueprints da aplicação. ``register_blueprints`` é chamado pelo factory."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.routes.ativos import bp as ativos_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.categorias import bp as categorias_bp
    from app.routes.compras import bp as compras_bp
    from app.routes.definicoes import bp as definicoes_bp
    from app.routes.emprestimos import bp as emprestimos_bp
    from app.routes.estoque import bp as estoque_bp
    from app.routes.localizacoes import bp as localizacoes_bp
    from app.routes.main import bp as main_bp
    from app.routes.produtos import bp as produtos_bp
    from app.routes.publico import bp as publico_bp
    from app.routes.setores import bp as setores_bp
    from app.routes.transferencias import bp as transferencias_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(setores_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(localizacoes_bp)
    app.register_blueprint(produtos_bp)
    app.register_blueprint(definicoes_bp)
    app.register_blueprint(estoque_bp)
    app.register_blueprint(transferencias_bp)
    app.register_blueprint(ativos_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(publico_bp)
    app.register_blueprint(emprestimos_bp)
