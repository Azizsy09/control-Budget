from odoo import api, fields, models, _
from odoo.tools import ustr
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)
import json 
from collections import defaultdict
from datetime import timedelta
import itertools

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.osv.expression import AND


class CrossoveredBudget(models.Model):
    _inherit = "crossovered.budget"

    # line_ids = fields.One2many('account.budget.line', 'budget_id', string="Account Budget Lines")
  #  @api.multi
    def button_export_xlsx(self):
        self.ensure_one()
        report_type = 'xlsx'
        return self._export(report_type)

    def _export(self, report_type):
        """Default export is PDF."""
        model = self.env['report_crossovered_budget']
        report = model.create(self._prepare_report_crossovered_budget())
        report.compute_data_for_report()
        return report.print_report(report_type)

    def _prepare_report_crossovered_budget(self):
       
        lines = []
        for line in self.crossovered_budget_line:
            lines.append((0, 0, {
                                    'general_budget': line.general_budget_id.name,
                                    'account_analytic': line.analytic_account_id.name,
                                    'planned_amount': line.planned_amount,
                                    'theoritical_amount': line.theoritical_amount,
                                    'practical_amount': line.practical_amount,
                                    'available_amount': line.available_amount,
                                    'practical_amount_without_invoice_document':line.practical_amount_without_invoice_document,
                                    'engage_without_invoice':line.engage_without_invoice

                                }))
        _logger.info(lines)
        return {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
            'line_ids': lines,
        }

class CrossoveredBudgetLines(models.Model):
    _inherit = "crossovered.budget.lines"

    engage_without_invoice = fields.Float(string='Montant Engage non realisé',compute='_compute_engage_amount_without_invoice', digits=0, store = False)
    engage_amount = fields.Float(string='Montant Engage',compute='_compute_engage_amount', digits=0, store = False)
    available_amount = fields.Float(compute='_compute_available_amount', string='Montant Disponible', digits=0)
    practical_amount_without_invoice_document = fields.Monetary(
    compute='_compute_practical_amount_without_invoice_document', string='Réalisé sans engagement', help="Réalisé sans engagement.")
    
    Avancement = fields.Float(
        compute='_compute_avancement', 
        string='Avancement', 
        store=False, 
        help="% = (Prevu - Disponible)/Prevu."
    )
    
    @api.onchange('available_amount')
    def _compute_avancement(self):
        _logger.info("Entrer dans la fonction _compute_avancement")
        for line in self:
            if line.planned_amount:
                line.Avancement = float((line.planned_amount - line.available_amount) / line.planned_amount)
                _logger.info(f"Calcul Avancement pour la ligne {line.id}: {line.Avancement}")
            else:
                line.Avancement = 0
    
     # Cette méthode forcera le calcul de l'Avancement pour tous les enregistrements
    
    
    @api.model
    def _get_query_account_analytic_line_without_invoice(self, model, account_fname, date_from, date_to, account_ids):
        # Construction du domaine
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            (account_fname, 'in', list(account_ids))
            
           
        ]
        if model == 'account.analytic.line':
            _logger.info("Domain for model account analytic by aziz09 ': %")
            domain += [('move_line_id.move_id.invoice_origin', '=', False)]
            
           
        if model == 'account.move.line':
            fname = '-balance'
            general_account = 'account_id'
            domain += [('parent_state', '=', 'draft')]
            # domain.append(('move_id.invoice_origin', '=', False)) 
            # domain += [('action_view_source_purchase_orders', '=', False)]
        else:
            fname = 'amount'
            general_account = 'general_account_id'

        # Log domaine
        _logger.info("Domain for model '%s': %s", model, domain)

        # Génération de la requête
        query = self.env[model]._search(domain)
        query.order = None
        query_str, params = query.select('%s', '%s', '%s', '%s', account_fname, general_account, f'SUM({fname})')
        params = [model, account_fname, date_from, date_to] + params
        query_str += f" GROUP BY {account_fname}, {general_account}"

        # Log requête SQL
        _logger.info("Generated SQL Query: %s", query_str)
        _logger.info("Query Parameters: %s", params)

        return query_str, params

    def _compute_practical_amount_without_invoice_document(self):
        groups = defaultdict(lambda: defaultdict(set))  # {(model, fname): {(date_from, date_to): account_ids}}
        for line in self:
            model, fname, accounts = self._get_accounts_from_line(line)

            # Log des comptes et des paramètres de la ligne
            _logger.info("Processing line: %s", line)
            _logger.info("Model: %s, Field Name: %s, Accounts: %s", model, fname, accounts)

            groups[(model, fname)][(line.date_from, line.date_to)].update(accounts)

        queries = []
        queries_params = []
        for (model, fname), by_date in groups.items():
            for (date_from, date_to), account_ids in by_date.items():
                # Log des paramètres de la requête avant de la générer
                _logger.info("Generating query for Model: %s, Field: %s, Date From: %s, Date To: %s, Accounts: %s",
                             model, fname, date_from, date_to, account_ids)

                query, params = self._get_query_account_analytic_line_without_invoice(model, fname, date_from, date_to, account_ids)
                queries.append(query)
                queries_params += params

        # Exécution des requêtes SQL
        final_query = " UNION ALL ".join(queries)
        _logger.info("Final SQL Query: %s", final_query)
        _logger.info("Query Parameters: %s", queries_params)

        self.env.cr.execute(final_query, queries_params)

        # Récupération des résultats
        agg_general = defaultdict(lambda: defaultdict(float))  # {(model, date_from, date_to): {(analytic, general): amount}}
        agg_analytic = defaultdict(lambda: defaultdict(float))  # {(model, date_from, date_to): {analytic: amount}}
        results = self.env.cr.fetchall()

        # Log des résultats
        _logger.info("Query Results: %s", results)

        for model, fname, date_from, date_to, account_id, general_account_id, amount in results:
            agg_general[(model, fname, date_from, date_to)][(account_id, general_account_id)] += amount
            agg_analytic[(model, fname, date_from, date_to)][account_id] += amount

        # Calcul des montants pour chaque ligne
        for line in self:
            model, fname, accounts = self._get_accounts_from_line(line)
            general_accounts = line.general_budget_id.account_ids

            _logger.info("Computing practical amount for line: %s", line)
            _logger.info("General Accounts: %s", general_accounts.ids if general_accounts else "None")
            _logger.info("Accounts: %s", accounts)

            if general_accounts:
                line.practical_amount_without_invoice_document = sum(
                    agg_general.get((model, fname, line.date_from, line.date_to), {}).get((account, general_account), 0)
                    for account in accounts
                    for general_account in general_accounts.ids
                )
            else:
                line.practical_amount_without_invoice_document = sum(
                    agg_analytic.get((model, fname, line.date_from, line.date_to), {}).get(account, 0)
                    for account in accounts
                )

            # Log du montant calculé
            _logger.info("Line %s: Practical Amount = %s", line, line.practical_amount_without_invoice_document)

    @api.onchange('engage_amount')
    def _compute_engage_amount_without_invoice(self):
        for line in self:
            result = 0.0
            result_without_invoice = 0.0
            # if not line.analytic_account_id:
            #     raise UserError(_("The Budget '%s' has no accounts!") % ustr(line.general_budget_id.name))

            date_from = line.date_from
            date_to = line.date_to
            account_ids = line.general_budget_id.account_ids.ids
            _logger.warning("line general_budget_id account_ids ids: %s",line.general_budget_id.account_ids.ids)
            
            purchase_order_lines_without_invoice = self.env['purchase.order.line'].search([
                ('date_planned', '>=', date_from),
                ('date_planned', '<=', date_to),
                ('account_id', 'in', account_ids),  # Filtrer par les comptes liés
                ('analytic_distribution', '=', line.analytic_account_id.name),
                ('state', 'in', ['purchase', 'done']),
                ('order_id.invoice_status', '=', 'to invoice')

            ])
            _logger.warning("order_id.action_create_invoice: %s",purchase_order_lines_without_invoice)
            
            result += sum(purchase_order_lines_without_invoice.mapped('price_subtotal')) or 0.0
            # result_without_invoice += sum(purchase_order_lines_wtihout_invoice.mapped('price_subtotal')) or 0.0

            # line.engage_without_invoice = result - result_without_invoice
            if line.engage_amount:
            
                line.engage_without_invoice = result
            else:
                line.engage_without_invoice = 0
    def _compute_engage_amount(self):
        for line in self:
            result = 0.0

            # if not line.analytic_account_id:
            #     raise UserError(_("The Budget '%s' has no accounts!") % ustr(line.general_budget_id.name))

            date_from = line.date_from
            date_to = line.date_to
            account_ids = line.general_budget_id.account_ids.ids
            _logger.warning("line general_budget_id account_ids ids: %s",line.general_budget_id.account_ids.ids)
            purchase_order_lines = self.env['purchase.order.line'].search([
                ('date_planned', '>=', date_from),
                ('date_planned', '<=', date_to),
                ('account_id', 'in', account_ids),  # Filtrer par les comptes liés
                ('analytic_distribution', '=', line.analytic_account_id.name),
                ('state', 'in', ['purchase', 'done'])
            ])

            result += sum(purchase_order_lines.mapped('price_subtotal')) or 0.0

            line.engage_amount = result


          

    #@api.multi
    def _compute_available_amount(self):
        for line in self:
            if line.practical_amount > 0:
                if line.engage_amount >= line.practical_amount:
                    line.available_amount = line.planned_amount - line.engage_amount - line.practical_amount_without_invoice_document
                else:
                    line.available_amount = line.planned_amount - line.practical_amount - abs(line.practical_amount_without_invoice_document)
            else:
                if line.engage_amount >= -line.practical_amount:
                    line.available_amount = line.planned_amount - line.engage_amount - abs(line.practical_amount_without_invoice_document)
                else:
                    line.available_amount = line.planned_amount - line.engage_amount + line.practical_amount_without_invoice_document


class AccountBudgetLine(models.Model):
    _name = 'account.budget.line'
    _description = 'Budget Line'
    _order = 'date desc, id desc'

    @api.model
    def _default_user(self):
        return self.env.context.get('user_id', self.env.user.id)

    name = fields.Char('Description', required=True)
    date = fields.Date('Date', required=True, index=True, default=fields.Date.context_today)
    unit_amount = fields.Float('Quantite', default=0.0)
    general_budget_id = fields.Many2one('account.budget.post', 'Poste budgétaire')
    account_id = fields.Many2one('account.analytic.account', 'Analytic Account', required=False, index=False)
    user_id = fields.Many2one('res.users', string='User', default=_default_user)
    # tag_ids = fields.Many2many('account.analytic.tag', string='Tags', copy=True)
    company_id = fields.Many2one(related='account_id.company_id', string='Company', store=True, readonly=True)
    amount = fields.Monetary(currency_field='company_currency_id', string="Montant Engage")
    planned_amount = fields.Float(string='Montant Prevu', digits=0)
    available_amount = fields.Float(string='Montant Disponible', digits=0)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    product_id = fields.Many2one('product.product', string='Product')
    general_account_id = fields.Many2one('account.account', string='Financial Account', readonly=True)
    move_id = fields.Many2one('purchase.order.line', string='Move Line', ondelete='cascade', index=True)
    code = fields.Char(size=8)
    ref = fields.Char(string='Ref.')
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True,
        help='Utility field to express amount currency')
    partner_id = fields.Many2one('res.partner', string='Fournisseur', store=True, readonly=True)