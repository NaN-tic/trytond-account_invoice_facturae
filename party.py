# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


class Address(metaclass=PoolMeta):
    __name__ = 'party.address'

    facturae_person_type = fields.Selection([
            (None, ''),
            ('J', 'Legal Entity'),
            ('F', 'Individual'),
            ], 'Person Type', sort=False)
    facturae_residence_type = fields.Selection([
            (None, ''),
            ('R', 'Resident in Spain'),
            ('U', 'Resident in other EU country'),
            ('E', 'Foreigner'),
            ], 'Residence Type', sort=False)
    oficina_contable = fields.Char('Oficina contable')
    organo_gestor = fields.Char('Organo gestor')
    unidad_tramitadora = fields.Char('Unidad tramitadora')
    organo_proponente = fields.Char('Organo proponente')

    @classmethod
    def __register__(cls, module_name):
        pool = Pool()
        Party = pool.get('party.party')
        address_table = cls.__table__()
        party_table = Party.__table__()
        party = Party.__table_handler__()
        cursor = Transaction().connection.cursor()

        super().__register__(module_name)

        # Migrat facturae fields from party to invoice addresses or in case of
        # missing the fist address.
        if party.column_exist('facturae_person_type'):
            cursor.execute(*party_table.select(
                party_table.id,
                where=party_table.facturae_person_type != None))
            addresses_update = []
            for party_id in cursor.fetchall():
                cursor.execute(*address_table.select(
                    address_table.id, address_table.invoice,
                    where=address_table.party.in_(party_id)))
                addresses = cursor.fetchall()
                addresses = {a[0]: a[1] for a in addresses}
                if not addresses:
                    continue
                if len(addresses) == 1:
                    addresses_update.append(next(iter(addresses)))
                else:
                    for address, invoice in addresses.items():
                        if invoice:
                            addresses_update.append(address)
                    if not any(addresses.values()):
                        addresses_update.extend(addresses)

            for address_update in addresses_update:
                cursor.execute(*address_table.select(
                        address_table.party,
                        where=address_table.id == address_update))
                party_id = cursor.fetchone()

                cursor.execute(*party_table.select(
                        party_table.facturae_person_type,
                        party_table.facturae_residence_type,
                        party_table.oficina_contable,
                        party_table.organo_gestor,
                        party_table.unidad_tramitadora,
                        party_table.organo_proponente,
                        where=party_table.id == party_id))
                party_values = cursor.fetchone()

                cursor.execute(*address_table.update(
                        columns=[
                            address_table.facturae_person_type,
                            address_table.facturae_residence_type,
                            address_table.oficina_contable,
                            address_table.organo_gestor,
                            address_table.unidad_tramitadora,
                            address_table.organo_proponente
                            ],
                        values=[
                            party_values[0],
                            party_values[1],
                            party_values[2],
                            party_values[3],
                            party_values[4],
                            party_values[5],
                            ],
                        where=address_table.id == address_update))

            party.drop_column('facturae_person_type')
            party.drop_column('facturae_residence_type')
            party.drop_column('oficina_contable')
            party.drop_column('organo_gestor')
            party.drop_column('unidad_tramitadora')
            party.drop_column('organo_proponente')
