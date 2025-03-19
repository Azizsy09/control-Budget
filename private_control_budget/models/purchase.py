from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare
from odoo.exceptions import UserError, AccessError, ValidationError
from odoo.tools.misc import formatLang
#from odoo.addons import decimal_precision as dp
import logging
import json

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
   
    _inherit = "purchase.order"

   
    crossovered_budget_line = fields.One2many('crossovered.budget.lines', 'analytic_account_id','Budgets',compute='_get_lines', store=False)
    amount_total_to_word = fields.Char(compute='_compute_amount_total_to_word', store=True) 
    check_budget_admin = fields.Boolean(compute='_compute_check_budget_admin')
    
    
    def _compute_check_budget_admin(self):
        self.check_budget_admin = False
        for record in self:
            user = self.env.user
            group = self.env['res.groups'].search([('id', '=', self.env.ref('private_control_budget.group_control_gestion_admininistrateur').id)])
            verify_group = True if user in group.users else False
            _logger.warning("verifier les group admin %s",verify_group)
            if user in group.users and record.order_line.check_budget_limit_admin:
                self.check_budget_admin = True
    
    
    
    
    # def verify_group(self):
    #     """
    #     Vérifie si l'utilisateur a les droits nécessaires pour valider la commande.
    #     :return: Boolean
    #     """
    #     self.ensure_one()
    #     _logger.info("verifie si user has access %ss",self.env.user.has_group("private_control_budget.group_control_gestion_admin"))
    #     return self.env.user.has_group("private_control_budget.group_control_gestion_admin")
    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            result = super(PurchaseOrder, self).button_confirm()
            # Valider la distribution analytique pour chaque ligne de commande
            order.order_line._validate_analytic_distribution()
            user = self.env.user
            group = self.env['res.groups'].search([('id', '=', self.env.ref('private_control_budget.group_control_gestion_admininistrateur').id)])
            verify_group = True if user in group.users else False
            _logger.warning("verifier les group %s",verify_group)
            if user not in group.users:
            # if not order.verify_group():
                _logger.warning("verifier les users %s",user)
                _logger.warning("Utilisateur %s n'a pas les droits pour valider la commande %s", self.env.user.name, order.name)
                order.order_line._check_budget_limit()
                order.order_line._get_available()
                

            # Ajouter le fournisseur au produit
            order._add_supplier_to_product()
            _logger.info("entrer dans fonction buttun confirm sans if")
            # Créer des lignes budgétaires pour chaque ligne de commande
            if order.crossovered_budget_line:
                
                _logger.info("entrer dans fonction buttun confirm")
                for crossovered_line in order.crossovered_budget_line:
                    # Appeler la méthode create_budget_lines pour chaque ligne de commande
                    for line in order.order_line:
                        line.create_budget_lines(
                            crossovered_line.general_budget_id.id, 
                            crossovered_line.analytic_account_id.id, 
                            crossovered_line.general_budget_id.account_ids.ids
                        )

            # Abonnez le partenaire de la commande aux messages
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])

            # Change l'état de la commande à 'confirmed'
            

        return result

    

        # @api.onchange('analytique_distribution')
        # def _budget_control(self):
        #     _logger.info("control du budget:")
            
                

        # @api.onchange('order_line')
        # def _budget_control(self):
        #     if self.order_line.analytic_distribution and self.crossovered_budget_line:
        #         if self.order_line.price_subtotal > self.crossovered_budget_line.available_amount :
        #             raise UserError(_('Attention votre budget est insuffisant vour effectuer l\'achat'''))
                
            
    #         if self.order_line.price_subtotal :
    #             _logger.warning("valeur price_subtotal: %s",self.order_line.price_subtotal)
    #             _logger.warning("valeur available_amount : %s",self.crossovered_budget_line.available_amount)
            

    @api.depends('order_line')
    def _analytic_distribution_key(self):
        
        
        for line in self.order_line:
            if isinstance(line.analytic_distribution, dict):
                analytic_distribution_key = next(iter(line.analytic_distribution))
                self.analytic_distribution_key = analytic_distribution_key  
                _logger.info("Clé de analytic_distribution_test : %s", analytic_distribution_key)
            else:
                _logger.warning("analytic_distribution n'est pas un dictionnaire  test: %s", line.analytic_distribution)


    to_19_fr = ( u'zĂŠro',  'un',  'deux',  'trois', 'quatre',   'cinq',   'six',
          'sept', 'huit', 'neuf', 'dix',   'onze', 'douze', 'treize',
          'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf' )
    tens_fr  = ( 'vingt', 'trente', 'quarante', 'Cinquante', 'Soixante', 'Soixante-dix', 'Quatre-vingts', 'Quatre-vingt Dix')
    denom_fr = ( '',
              'Mille',     'Millions',         'Milliards',       'Billions',       'Quadrillions',
              'Quintillion',  'Sextillion',      'Septillion',    'Octillion',      'Nonillion',
              'DĂŠcillion',    'Undecillion',     'Duodecillion',  'Tredecillion',   'Quattuordecillion',
              'Sexdecillion', 'Septendecillion', 'Octodecillion', 'Icosillion', 'Vigintillion' )

    
    purchase_user_id = fields.Many2one(
        'res.users',
        string='Purchase User',
        compute='_set_purchase_user',
        store=True,
    )

    @api.depends('state')
    def _set_purchase_user(self):
        for rec in self:
            if rec.state == 'draft' or 'sent':
                rec.purchase_user_id = self.env.user.id,
    
    @api.depends('order_line')
    def _get_lines(self):
        temoin = []
        self.crossovered_budget_line = []
        self.order_line = []
        
        for line in self.order_line:
            if isinstance(line.analytic_distribution, dict):
                analytic_distribution_key = next(iter(line.analytic_distribution))
                _logger.info("Clé de analytic_distribution : %s", analytic_distribution_key)
            else:
                _logger.warning("analytic_distribution n'est pas un dictionnaire : %s", line.analytic_distribution)

        # for line in self.order_line:
        #     for key, value in line.analytic_distribution.items():
        #         _logger.info("Contenu de analytic_distribution - Clé: %s, Valeur: %s" % (key, value))
        
        for line in self.order_line:
            # analytic_distribution_dict = line.analytic_distribution
            # analytic_distribution_data = json.loads(analytic_distribution_dict)
            # analytic_distribution_key = next(iter(analytic_distribution_data))
            # _logger.info("Ce code va maider a voir le contenenu de analytic_distribution  => ",analytic_distribution_key)
            if isinstance(line.analytic_distribution, dict):
                analytic_distribution_key = next(iter(line.analytic_distribution))
                _logger.info("Clé de analytic_distribution11 : %s", analytic_distribution_key)
                # ('general_budget_id.account_ids','=',line.account_id.id)
                
                _logger.info("Clé de analytic account name : %s",line.analytic_distribution_name)
                budgets = self.env['crossovered.budget.lines'].search([('analytic_account_id','=',line.analytic_distribution_name),('general_budget_id.account_ids','=',line.account_id.id),('date_from', '<',self.date_order),('date_to', '>=',self.date_order)])

                _logger.info("Contenu de budgets : %s", budgets)
                if budgets:
                    for budget in budgets:
                        if budget.id not in temoin:
                            _logger.info("budget_id => %s , temoin => %s",budget.id, temoin)
                            self.crossovered_budget_line += budget
                            temoin.append(budget.id)
            else:
                _logger.warning("analytic_distribution n'est pas un dictionnaire : %s", line.analytic_distribution)
                

    def _convert_nn_fr(self, val):
        """ convert a value < 100 to French
        """
        if val < 20:
            return self.to_19_fr[val]
        for (dcap, dval) in ((k, 20 + (10 * v)) for (v, k) in enumerate(self.tens_fr)):
            if dval + 10 > val:
                if val % 10:
                    return dcap + '-' + self.to_19_fr[val % 10]
                return dcap

    def _convert_nnn_fr(self, val):
        """ convert a value < 1000 to french

            special cased because it is the level that kicks
            off the < 100 special case.  The rest are more general.  This also allows you to
            get strings in the form of 'forty-five hundred' if called directly.
        """
        word = ''
        (mod, rem) = (val % 100, val // 100)
        if rem > 0:
            word = self.to_19_fr[rem] + ' Cent'
            if mod > 0:
                word += ' '
        if mod > 0:
            word += self._convert_nn_fr(mod)
        return word

    def french_number(self, val):
        if val < 100:
            return self._convert_nn_fr(val)
        if val < 1000:
             return self._convert_nnn_fr(val)
        for (didx, dval) in ((v - 1, 1000 ** v) for v in range(len(self.denom_fr))):
            if dval > val:
                mod = 1000 ** didx
                l = val // mod
                r = val - (l * mod)
                ret = self._convert_nnn_fr(l) + ' ' + self.denom_fr[didx]
                if r > 0:
                    ret = ret + ', ' + self.french_number(r)
                return ret

    def amount_to_text_fr(self, number, currency):
        number = '%.2f' % number
        units_name = currency
        list = str(number).split('.')
        start_word = self.french_number(abs(int(list[0])))
        end_word = self.french_number(int(list[1]))
        cents_number = int(list[1])
        cents_name = (cents_number > 1) and ' Cents' or ' Cent'
        final_result = start_word +' '+units_name+' '+ end_word +' '+cents_name
        return final_result

    #@api.multi
    @api.depends('amount_total')
    def _compute_amount_total_to_word(self):
        for record in self:
            record.amount_total_to_word = record.amount_to_text_fr(record.amount_total, currency='')[:-10]

   # @api.multi
    @api.constrains('crossovered_budget_line','order_line')
    def _control_budget_date(self):
        _logger.info("entrer dans fonction")
        for record in self:
            for crossovered_line in record.crossovered_budget_line:
                for line in record.order_line:
                    if line.analytic_distribution == crossovered_line.analytic_account_id and line.account_id in crossovered_line.general_budget_id.account_ids and (line.date_planned.date() < crossovered_line.date_from or line.date_planned.date() > crossovered_line.date_to):
                        raise ValidationError(_("La date prevu n'est pas comprise dans la plage du poste budgetaire"))
        return True

   # @api.multi
    def button_cancel(self):
        for order in self:
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise UserError(_("Unable to cancel this purchase order. You must first cancel the related vendor bills."))
        self.env['account.budget.line'].search([('ref','=',order.name)]).unlink()
        self.write({'state': 'cancel'})

 
class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    analytic_distribution_name = fields.Integer(
        string='analytic_distribution_name',compute='_analytic_distribution_name', store=True)

    account_id = fields.Many2one('account.account', string='Compte',
         domain=[('deprecated', '=', False)],
        help="The income or expense account related to the selected product.")
    account_income_id = fields.Many2one('account.account', string='Compte de revenus', 
                                       related='product_id.property_account_income_id',
                                       store=True, readonly=True)
    available =  fields.Float(string='Montant budget restant',compute="_get_available", digits=0 , default="0")

    planned =  fields.Float(string='Montant budget prevu',compute="_get_planned", digits=0 , default="0")

    analytic_budget_ids = fields.One2many('account.budget.line', 'move_id', string='Account Budget lines')

    @api.depends('analytic_distribution')
    def _analytic_distribution_name(self):
        
        
        for line in self:
            if isinstance(line.analytic_distribution, dict):
                analytic_distribution_name = next(iter(line.analytic_distribution))
                line.analytic_distribution_name = analytic_distribution_name  
                _logger.info("Clé de analytic_distribution_test : %s", analytic_distribution_name)
            else:
                _logger.warning("analytic_distribution n'est pas un dictionnaire  test: %s", line.analytic_distribution)

    @api.onchange('product_id')
    def onchange_product_id(self):
        result = {}
        if not self.product_id:
            return result

        # Reset date, price and quantity since _onchange_quantity will provide default values
        self.date_planned = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        self.price_unit = self.product_qty = 0.0
        self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
        self.account_id = self.product_id.property_account_expense_id.id or self.product_id.categ_id.property_account_expense_categ_id.id
        result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}

        product_lang = self.product_id.with_context({
            'lang': self.partner_id.lang,
            'partner_id': self.partner_id.id,
        })
        self.name = product_lang.display_name
        if product_lang.description_purchase:
            self.name += '\n' + product_lang.description_purchase

        fpos = self.order_id.fiscal_position_id
        if self.env.uid == SUPERUSER_ID:
            company_id = self.env.user.company_id.id
            self.taxes_id = fpos.map_tax(self.product_id.supplier_taxes_id.filtered(lambda r: r.company_id.id == company_id))
        else:
            self.taxes_id = fpos.map_tax(self.product_id.supplier_taxes_id)

        self._suggest_quantity()
        # self._onchange_quantity()

        return result

    
    # @api.depends('account_id', 'analytic_distribution')
    def _get_available(self):
        for record in self:
            available_amount = 0.0
            has_budget = False  # Flag pour vérifier s'il y a un budget défini

            # Vérification si analytic_distribution est un dictionnaire
            if isinstance(record.analytic_distribution, dict):
                for analytic_account_id, percentage in record.analytic_distribution.items():
                    # Convertir l'ID en un enregistrement réel
                    analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))

                    # Vérifier si l'ID est valide et accéder aux lignes de budget
                    if analytic_account and analytic_account.exists():
                        for budget_line in analytic_account.crossovered_budget_line:
                             if record.account_id.id in budget_line.general_budget_id.account_ids.ids:
                                available_amount += budget_line.available_amount * (percentage / 100)
                                has_budget = True
                                _logger.info("Available amount: %s", budget_line.available_amount)

            # Bloquer si aucun budget n'est trouvé
            if  record.analytic_distribution and not has_budget:
                raise UserError(f"Aucun budget prevu pour le compte {analytic_account.name}")

            # Affecter le montant disponible calculé
            record.available = available_amount


   # @api.multi
    # @api.depends('account_id', 'analytic_distribution')
    # def _get_available(self):
    #     self.available = 0
    #     _logger.info("Entrer dans fonction : get limit")
    #     for record in self:
    #         if record.account_id and record.analytic_distribution and isinstance(record.analytic_distribution, models.Model):
    #             for line in record.analytic_distribution.crossovered_budget_line:
    #                 if record.account_id.id in line.general_budget_id.account_ids.ids:
    #                     record.available = line.available_amount
    #                     _logger.info("Entrer dans fonction : get limit %s",record.available)
    #                     break
    #         _logger.info("Entrer dans  : record.available %s",record.available)

  #  @api.multi
    # @api.depends('account_id','analytic_distribution')
    def _get_planned(self):
                    for record in self:
                        for analytic_account_id, percentage in record.analytic_distribution.items():
                    # Convertir l'ID en un enregistrement réel
                            self.planned = 0
                            analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))
                            if record.account_id and analytic_account:
                                for line in analytic_account.crossovered_budget_line:
                                    if record.account_id.id in line.general_budget_id.account_ids.ids:
                                        record.planned = line.planned_amount
                                        break


    # @api.constrains('price_subtotal', 'analytic_distribution', 'available')
    def _check_budget_limit(self):
        for record in self:
            _logger.info("Entrer dans fonction : check limit")
           
            if record.available < record.price_subtotal:
                if isinstance(record.analytic_distribution, dict):
                    for analytic_account_id, percentage in record.analytic_distribution.items():
                        # Convertir l'ID en un enregistrement réel
                        analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))

                        
                    message = _(f'le montant saisi {record.price_subtotal} dépasse le budget disponible {record.available} pour le compte {analytic_account.name}')
                    
                    raise UserError(message)

    

  #  @api.multi
    def create_budget_lines(self, general_budget_id, analytic_account_id, ids):
        """ Create analytic items upon validation of an account.move.line having an budget account. This
            method first remove any existing analytic item related to the line before creating any new one.
        """
        _logger.info('entrer dans fonction create budget')
        for obj_line in self:
            _logger.info("voir obj_line %s",obj_line)
            _logger.info("Retour de _prepare_budget_line: %s", obj_line._prepare_budget_line(general_budget_id))
            # Au lieu de faire obj_line._prepare_budget_line(general_budget_id)[0], faites :
            

            # vals_line = obj_line._prepare_budget_line(general_budget_id)[0]
            vals_line = []
            obj_line.analytic_distribution == analytic_account_id
            # self.env['account.budget.line'].create(vals_line)
            if  obj_line.account_id.id in ids:
                vals_line = obj_line._prepare_budget_line(general_budget_id)
            _logger.info("fonction nest pas exute")
            # Ensuite, vous pouvez créer la ligne budgétaire avec le dictionnaire retourné.
                  
            self.env['account.budget.line'].create(vals_line)
            #     vals_line = obj_line._prepare_budget_line(general_budget_id)[0]
            #     _logger.info('La fonction nest pas exute')
            #     self.env['account.budget.line'].create(vals_line)
            # else:
            #     _logger.info('La fonction nest pas exute')


   # @api.one
    def _prepare_budget_line(self, general_budget_id):
        """ Prepare the values used to create() an account.budget.line. """

        # Initialisation d'une liste pour stocker les lignes budgétaires à retourner
        budget_lines = []

        # Vérification si 'analytic_distribution' contient des comptes analytiques
        if self.analytic_distribution:
            # Itération sur les comptes analytiques dans 'analytic_distribution'
            for analytic_account_id, percentage in self.analytic_distribution.items():
                # Convertir l'ID en un enregistrement réel (objet)
                analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))
                
                # Préparation des valeurs à retourner pour la ligne budgétaire
                values = {
                    'name': self.name,
                    'date': self.date_planned,
                    'account_id': analytic_account.id or False,  # Utilisation de l'ID du compte analytique
                    'unit_amount': self.product_qty,
                    'product_id': self.product_id.id or False,
                    'amount': self.price_subtotal,
                    'available_amount': (self.available - self.price_subtotal),
                    'planned_amount': self.planned,
                    'general_budget_id': general_budget_id or False,
                    'general_account_id': self.account_id.id or False,
                    'ref': self.order_id.name,
                    'partner_id': self.order_id.partner_id.id,
                }

                # Ajout de la ligne préparée dans la liste
                _logger.info("valueeeee %s",values)
                budget_lines.append(values)

        else:
            _logger.warning("Aucun compte analytique trouvé dans 'analytic_distribution'.")

        # Retourner toutes les lignes budgétaires préparées
        return budget_lines
