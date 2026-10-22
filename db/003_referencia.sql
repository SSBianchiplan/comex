SET search_path = comex, public;

INSERT INTO ref_tipo_conteiner VALUES
 ('20DV','20'' Dry',       5898, 2352, 2393, 2340, 2280, 2230, 28230, false, false, 0,   20),
 ('40DV','40'' Dry',      12032, 2352, 2393, 2340, 2280, 3750, 26730, false, false, 0,   40),
 ('40HC','40'' High Cube',12032, 2352, 2698, 2340, 2585, 3900, 26580, false, false, 0,   40),
 ('40OT','40'' Open Top', 12032, 2350, 2350, 2340, 2270, 4000, 26480, true,  false, 600, 40),
 ('40FR','40'' Flat Rack',12080, 2420, 1950, NULL, NULL, 5000, 40000, true,  true,  2250,40);

INSERT INTO ref_tipo_embalagem VALUES
 ('crate','Caixa fechada ISPM-15 + barreira de alumínio + dessecante',1.000,true),
 ('caixa','Caixa de compensado fechada + VCI + dessecante',1.000,true),
 ('engradado','Engradado ripado ISPM-15 + filme VCI',0.450,false);

INSERT INTO ref_ncm VALUES
 ('8537.10.20','Controladores programáveis'),
 ('8537.10.90','Quadros e painéis para tensão até 1.000 V — outros'),
 ('8537.20.90','Quadros e painéis para tensão superior a 1.000 V — outros'),
 ('8535.21.00','Disjuntores para tensão inferior a 72,5 kV'),
 ('8538.90.90','Partes para aparelhos das posições 85.35 a 85.37'),
 ('8504.40.90','Conversores estáticos (inversores de frequência)'),
 ('9403.20.90','Móveis de metal — outros');

INSERT INTO ref_rota (id,nome,porto_destino,pais,transito_dias,transbordo,tributo_pct,base_aduaneira,acordo,exige_co) VALUES
 ('USHOU','Houston, EUA','Port of Houston (Barbours Cut)','EUA',24,false,40.2,'FOB','Sem preferência — Section 301 25% + 12,5% + MFN 2,7%',false),
 ('USPEF','Port Everglades, EUA','Port Everglades (Miami)','EUA',20,false,40.2,'FOB','Sem preferência — Section 301 25% + 12,5% + MFN 2,7%',false),
 ('CLSAI','San Antonio, Chile','Puerto San Antonio','Chile',13,false,0,'CIF','ACE-35 Mercosul–Chile: 0% com certificado de origem',true),
 ('PECLL','Callao, Peru','Callao (DP World)','Peru',19,true,0,'CIF','ACE-58 Mercosul–Peru: 0% com certificado de origem',true),
 ('MXVER','Veracruz, México','Veracruz (ICAVE)','México',27,true,5,'CIF','Verificar ACE-53 por código — estimativa 5%',true),
 ('NLRTM','Rotterdam, Países Baixos','Rotterdam (Maasvlakte II)','Países Baixos',23,false,2.1,'CIF','TEC UE 8537: 2,1% — acordo Mercosul–UE: verificar vigência',false),
 ('AOLAD','Luanda, Angola','Porto de Luanda','Angola',22,true,10,'CIF','Pauta aduaneira angolana — estimativa 10%',false);

INSERT INTO ref_rota_frete (rota_id,tipo_conteiner,frete_usd,vigencia)
SELECT r, t, v, daterange('2026-07-01','2027-01-01') FROM (VALUES
 ('USHOU','20DV',2600),('USHOU','40DV',3600),('USHOU','40HC',3700),('USHOU','40OT',6200),('USHOU','40FR',7400),
 ('USPEF','20DV',2400),('USPEF','40DV',3300),('USPEF','40HC',3400),('USPEF','40OT',5800),('USPEF','40FR',6900),
 ('CLSAI','20DV',1400),('CLSAI','40DV',2100),('CLSAI','40HC',2200),('CLSAI','40OT',3900),('CLSAI','40FR',4800),
 ('PECLL','20DV',1700),('PECLL','40DV',2500),('PECLL','40HC',2600),('PECLL','40OT',4300),('PECLL','40FR',5300),
 ('MXVER','20DV',2700),('MXVER','40DV',3800),('MXVER','40HC',3900),('MXVER','40OT',6400),('MXVER','40FR',7600),
 ('NLRTM','20DV',1500),('NLRTM','40DV',2300),('NLRTM','40HC',2400),('NLRTM','40OT',4200),('NLRTM','40FR',5200),
 ('AOLAD','20DV',2800),('AOLAD','40DV',4300),('AOLAD','40HC',4400),('AOLAD','40OT',7000),('AOLAD','40FR',8200)
) x(r,t,v);

INSERT INTO ref_componente_custo VALUES
 ('emb','Embalagem ISPM-15 (caixas, barreira, dessecante)',1),
 ('carg','Estufagem, peação e lacre na fábrica',2),
 ('rodo','Rodoviário fábrica → porto de origem',3),
 ('despE','Despachante, DU-E e certificado de origem',4),
 ('thcO','THC / capatazia no terminal de origem',5),
 ('frete','Frete marítimo + BAF/EFS + ISPS + OOG + B/L',6),
 ('seg','Seguro de transporte (110% CIF)',7),
 ('thcD','THC no porto de destino',8),
 ('entrega','Rodoviário porto → site do cliente',9),
 ('desc','Descarga no local de destino',10),
 ('despI','Despachante de importação no destino',11),
 ('trib','Tributos de importação no destino',12);

INSERT INTO ref_incoterm VALUES
 ('EXW','Na fábrica do vendedor, sem carregar',false,NULL),
 ('FCA','Na fábrica, carregado no veículo do transportador do comprador',true,NULL),
 ('FOB','A bordo no porto de embarque — ICC não recomenda para contêiner',false,NULL),
 ('CPT','Na entrega ao primeiro transportador',true,NULL),
 ('CIP','Na entrega ao primeiro transportador — seguro ICC (A)',true,'ICC (A)'),
 ('CFR','A bordo no porto de embarque',false,NULL),
 ('CIF','A bordo no porto de embarque — seguro ICC (C)',false,'ICC (C)'),
 ('DAP','No local nomeado, sobre o veículo, pronto para descarga',true,NULL),
 ('DPU','No local nomeado, descarregado',true,NULL),
 ('DDP','No local nomeado, descarregado e desembaraçado',true,NULL);

INSERT INTO ref_incoterm_componente SELECT i, unnest(c) FROM (VALUES
 ('EXW','{emb}'::text[]), ('FCA','{emb,carg,despE}'), ('FOB','{emb,carg,rodo,despE,thcO}'),
 ('CPT','{emb,carg,rodo,despE,thcO,frete}'), ('CIP','{emb,carg,rodo,despE,thcO,frete,seg}'),
 ('CFR','{emb,carg,rodo,despE,thcO,frete}'), ('CIF','{emb,carg,rodo,despE,thcO,frete,seg}'),
 ('DAP','{emb,carg,rodo,despE,thcO,frete,seg,thcD,entrega}'),
 ('DPU','{emb,carg,rodo,despE,thcO,frete,seg,thcD,entrega,desc}'),
 ('DDP','{emb,carg,rodo,despE,thcO,frete,seg,thcD,entrega,desc,despI,trib}')
) x(i,c);

INSERT INTO ref_custo_param VALUES
 ('baf_20',300,'USD','BAF/EFS por contêiner 20'''),('baf_40',550,'USD','BAF/EFS por contêiner 40'''),
 ('oog_altura',900,'USD','Sobretaxa de sobre-altura (OOG)'),('oog_largura',1400,'USD','Sobretaxa de largura excedente (OOG)'),
 ('isps',18,'USD','ISPS por contêiner'),('bl',95,'USD','Emissão de B/L por embarque'),
 ('thcO_20',1350,'BRL','THC origem 20'''),('thcO_40',1650,'BRL','THC origem 40'''),('thcO_esp',2900,'BRL','THC origem OT/FR com guindaste'),
 ('rodo_20',2100,'BRL','Rodoviário até o porto 20'''),('rodo_40',2600,'BRL','Rodoviário até o porto 40'''),('rodo_OT',3200,'BRL','Rodoviário Open Top'),('rodo_FR',5200,'BRL','Rodoviário prancha Flat Rack'),
 ('estuf_20',900,'BRL','Estufagem e peação 20'''),('estuf_40',1400,'BRL','Estufagem e peação 40'''),('estuf_esp',2400,'BRL','Estufagem OT/FR'),
 ('thcD_20',420,'USD','THC destino 20'''),('thcD_40',620,'USD','THC destino 40'''),('fator_esp_dest',1.5,'UN','Multiplicador destino para OT/FR'),
 ('entrega_20',950,'USD','Entrega no site 20'''),('entrega_40',1150,'USD','Entrega no site 40'''),('entrega_esp',2600,'USD','Entrega no site OT/FR'),
 ('desp_br',1900,'BRL','Despachante exportação'),('co_br',180,'BRL','Certificado de origem'),('desp_dest',850,'USD','Despachante importação'),
 ('madeira_m3',2600,'BRL','Madeira HT por m³'),('mao_caixa',350,'BRL','Mão de obra por caixa'),('dessecante_un',3.5,'BRL','Unidade DIN de dessecante'),
 ('barreira_m2',28,'BRL','Barreira de alumínio por m²'),('vci_m2',6,'BRL','Filme VCI por m²');

INSERT INTO ref_feriado VALUES
 ('2026-01-01','Confraternização Universal','nacional'),('2026-02-16','Carnaval','ponto facultativo'),('2026-02-17','Carnaval','ponto facultativo'),
 ('2026-04-03','Sexta-feira Santa','nacional'),('2026-04-21','Tiradentes','nacional'),('2026-05-01','Dia do Trabalho','nacional'),
 ('2026-06-04','Corpus Christi','ponto facultativo'),('2026-09-07','Independência','nacional'),('2026-10-12','Nossa Senhora Aparecida','nacional'),
 ('2026-11-02','Finados','nacional'),('2026-11-15','Proclamação da República','nacional'),('2026-11-20','Consciência Negra','nacional'),
 ('2026-12-25','Natal','nacional'),('2027-01-01','Confraternização Universal','nacional'),('2027-02-08','Carnaval','ponto facultativo'),
 ('2027-02-09','Carnaval','ponto facultativo'),('2027-03-26','Sexta-feira Santa','nacional'),('2027-04-21','Tiradentes','nacional');

INSERT INTO ref_estado VALUES
 ('RASCUNHO',0,'Rascunho',false),('PLANEJADO',1,'Planejado',false),('FAT_APROVADO',2,'FAT aprovado',false),
 ('EMBALADO',3,'Embalado',true),('ESTUFADO',4,'Estufado e lacrado',true),('DESPACHADO',5,'DU-E registrada',true),
 ('NO_TERMINAL',6,'No terminal',true),('EMBARCADO',7,'Embarcado',true),('CHEGOU',8,'Chegou ao destino',true),
 ('DESEMBARACADO',9,'Desembaraçado',true),('ENTREGUE',10,'Entregue',true),('CANCELADO',99,'Cancelado',true);
INSERT INTO ref_transicao VALUES
 ('RASCUNHO','PLANEJADO'),('PLANEJADO','FAT_APROVADO'),('FAT_APROVADO','EMBALADO'),('EMBALADO','ESTUFADO'),
 ('ESTUFADO','DESPACHADO'),('DESPACHADO','NO_TERMINAL'),('NO_TERMINAL','EMBARCADO'),('EMBARCADO','CHEGOU'),
 ('CHEGOU','DESEMBARACADO'),('DESEMBARACADO','ENTREGUE'),
 ('RASCUNHO','CANCELADO'),('PLANEJADO','CANCELADO'),('FAT_APROVADO','CANCELADO'),('EMBALADO','CANCELADO');

INSERT INTO ref_etapa VALUES
 ('PEDIDO',1,'Pedido de exportação registrado','TransactionEvent','accepting','PLANEJADO',NULL,'Fábrica do exportador — Blumenau/SC'),
 ('PASSAPORTES',2,'Passaportes digitais dos volumes emitidos','ObjectEvent','commissioning','PLANEJADO',NULL,'Fábrica do exportador — Blumenau/SC'),
 ('FAT',3,'FAT aprovado pelo cliente','ObjectEvent','inspecting','FAT_APROVADO','fat','Bancada de testes — fábrica'),
 ('EMBALAGEM',4,'Embalagem concluída e inspecionada','ObjectEvent','packing','EMBALADO','insp','Expedição — fábrica'),
 ('ESTUFAGEM',5,'Estufagem, peação e lacre dos contêineres','AggregationEvent','loading','ESTUFADO','estuf','Expedição — fábrica'),
 ('DUE',6,'NF-e de exportação e DU-E registradas','TransactionEvent','accepting','DESPACHADO',NULL,'Portal Único Siscomex'),
 ('GATE_IN',7,'Gate-in no terminal e VGM transmitido','ObjectEvent','arriving','NO_TERMINAL','cut','Portonave — Navegantes/SC'),
 ('EMBARQUE',8,'Embarque — navio zarpou','ObjectEvent','departing','EMBARCADO','etd','Portonave — Navegantes/SC'),
 ('EBL',9,'eBL emitido e transferido (DCSA)','TransactionEvent','shipping','EMBARCADO','bl','Plataforma eBL'),
 ('CHEGADA',10,'Chegada ao porto de destino','ObjectEvent','arriving','CHEGOU','eta','Porto de destino'),
 ('DESEMBARACO',11,'Desembaraço de importação concluído','TransactionEvent','accepting','DESEMBARACADO','lib','Porto de destino'),
 ('ENTREGA',12,'Entrega no site e aceite do cliente','ObjectEvent','receiving','ENTREGUE','ent','Site do cliente');

INSERT INTO ref_documento VALUES
 ('INVOICE','Fatura comercial (Commercial Invoice)',NULL,1),
 ('PACKING','Packing list por volume (SSCC)',NULL,2),
 ('NFE_DUE','NF-e de exportação (CFOP 7101) e DU-E','despE',3),
 ('CO','Certificado de origem','despE',4),
 ('ISPM15','Declaração de tratamento ISPM-15','emb',5),
 ('BOOKING','Booking confirmation e instrução de embarque','frete',6),
 ('VGM','VGM — peso bruto verificado (SOLAS VI/2)','thcO',7),
 ('EBL','Conhecimento de embarque eletrônico (eBL DCSA)','frete',8),
 ('SEGURO','Apólice/certificado de seguro — ICC (A)','seg',9),
 ('FAT','Relatório de FAT e data book',NULL,10),
 ('IMPORT','Desembaraço de importação no destino','despI',11);
