-- Seed script: large randomized dataset for local/dev/demo use.
-- Creates:
--   - 300 businesses
--   - 10,000 orders
--   - 3-8 shipment events per order
--   - 1 notification per shipment event
--
-- Usage:
--   psql "$POSTGRES_CONNECTION_STRING?sslmode=require" -v ON_ERROR_STOP=1 -f migrations/seed_large_dataset.sql

BEGIN;

TRUNCATE TABLE notifications, shipment_events, orders, businesses CASCADE;

DO $$
DECLARE
    cities TEXT[] := ARRAY[
        'New York, NY','Los Angeles, CA','Chicago, IL','Houston, TX','Phoenix, AZ',
        'Philadelphia, PA','San Antonio, TX','San Diego, CA','Dallas, TX','San Jose, CA',
        'Austin, TX','Jacksonville, FL','San Francisco, CA','Columbus, OH','Indianapolis, IN',
        'Charlotte, NC','Seattle, WA','Denver, CO','Boston, MA','Nashville, TN',
        'Atlanta, GA','Miami, FL','Portland, OR','Las Vegas, NV','Detroit, MI',
        'Minneapolis, MN','Orlando, FL','Kansas City, MO','New Orleans, LA','Salt Lake City, UT'
    ];
    street_names TEXT[] := ARRAY[
        'Main St','Market St','Broadway','Maple Ave','Oak St','Pine St','Cedar Ave',
        'Washington Blvd','Madison Ave','Lakeview Dr','Sunset Blvd','River Rd',
        'Highland Ave','Park Ave','Franklin St','Jefferson St','Lincoln Blvd','Hill St'
    ];
    business_prefixes TEXT[] := ARRAY[
        'Apex','BlueRiver','Prime','Golden','Silver','NorthStar','Rapid','Summit',
        'Evergreen','Ironwood','Skyline','Metro','Pacific','Atlas','Liberty','Harbor',
        'Vertex','Beacon','Redwood','Pinnacle','Frontier','Velocity','Quantum','Sterling'
    ];
    business_suffixes TEXT[] := ARRAY[
        'Logistics','Traders','Supply Co','Distribution','Wholesale','Retail Group',
        'Commerce','Industrial','Manufacturing','Foods','Pharma','Electronics',
        'Apparel','Home Goods','Auto Parts','Medical Supply','Tech Supply','Office Supply'
    ];

    business_ids UUID[] := ARRAY[]::UUID[];
    business_count INT := 300;
    order_count INT := 10000;

    i INT;
    j INT;
    business_idx INT;
    city_idx INT;
    dest_idx INT;
    service_roll NUMERIC;
    event_roll NUMERIC;
    final_roll NUMERIC;
    event_count INT;

    v_business_id UUID;
    v_order_id UUID;
    v_tracking TEXT;
    v_origin TEXT;
    v_destination TEXT;
    v_service_type service_type;
    v_status order_status;
    v_event_type event_type;
    v_notification_type notification_type;
    v_created_at TIMESTAMPTZ;
    v_event_time TIMESTAMPTZ;
    v_estimated DATE;
    v_actual DATE;
    v_location TEXT;
    v_message TEXT;
BEGIN
    -- Businesses
    FOR i IN 1..business_count LOOP
        city_idx := 1 + floor(random() * array_length(cities, 1))::INT;

        INSERT INTO businesses (
            name,
            account_number,
            address,
            contact_email,
            phone,
            created_at
        )
        VALUES (
            format(
                '%s %s %s',
                business_prefixes[1 + floor(random() * array_length(business_prefixes, 1))::INT],
                business_suffixes[1 + floor(random() * array_length(business_suffixes, 1))::INT],
                i
            ),
            format(
                'ACC-%s-%s',
                lpad(i::TEXT, 4, '0'),
                upper(substr(md5(clock_timestamp()::TEXT || random()::TEXT), 1, 6))
            ),
            format(
                '%s %s, %s',
                (100 + floor(random() * 9800)::INT),
                street_names[1 + floor(random() * array_length(street_names, 1))::INT],
                cities[city_idx]
            ),
            format('ops+%s@seedbiz%s.com', i, 1 + floor(random() * 50)::INT),
            format('+1-555-%s-%s', lpad((100 + floor(random() * 900)::INT)::TEXT, 3, '0'), lpad((1000 + floor(random() * 9000)::INT)::TEXT, 4, '0')),
            NOW() - ((floor(random() * 365))::TEXT || ' days')::INTERVAL
        )
        RETURNING id INTO v_business_id;

        business_ids := array_append(business_ids, v_business_id);
    END LOOP;

    -- Orders + Events + Notifications
    FOR i IN 1..order_count LOOP
        business_idx := 1 + floor(random() * array_length(business_ids, 1))::INT;
        v_business_id := business_ids[business_idx];

        city_idx := 1 + floor(random() * array_length(cities, 1))::INT;
        dest_idx := 1 + floor(random() * array_length(cities, 1))::INT;
        WHILE dest_idx = city_idx LOOP
            dest_idx := 1 + floor(random() * array_length(cities, 1))::INT;
        END LOOP;

        v_origin := cities[city_idx];
        v_destination := cities[dest_idx];

        service_roll := random();
        v_service_type := CASE
            WHEN service_roll < 0.35 THEN 'FedEx Ground'::service_type
            WHEN service_roll < 0.62 THEN 'FedEx Express'::service_type
            WHEN service_roll < 0.74 THEN 'FedEx Overnight'::service_type
            WHEN service_roll < 0.89 THEN 'FedEx 2Day'::service_type
            ELSE 'FedEx International'::service_type
        END;

        v_created_at := NOW()
            - ((1 + floor(random() * 120))::TEXT || ' days')::INTERVAL
            - ((floor(random() * 24))::TEXT || ' hours')::INTERVAL
            - ((floor(random() * 60))::TEXT || ' minutes')::INTERVAL;

        v_estimated := (
            v_created_at
            + CASE v_service_type
                WHEN 'FedEx Overnight'::service_type THEN '1 day'::INTERVAL
                WHEN 'FedEx 2Day'::service_type THEN '2 days'::INTERVAL
                WHEN 'FedEx Express'::service_type THEN ((2 + floor(random() * 2))::TEXT || ' days')::INTERVAL
                WHEN 'FedEx Ground'::service_type THEN ((3 + floor(random() * 4))::TEXT || ' days')::INTERVAL
                ELSE ((6 + floor(random() * 6))::TEXT || ' days')::INTERVAL
            END
        )::DATE;

        v_tracking := format('TRK%s%s', to_char(clock_timestamp(), 'YYMMDDHH24MISSMS'), lpad(i::TEXT, 5, '0'));

        INSERT INTO orders (
            business_id,
            tracking_number,
            origin,
            destination,
            status,
            weight_lbs,
            service_type,
            estimated_delivery,
            created_at,
            updated_at
        )
        VALUES (
            v_business_id,
            v_tracking,
            v_origin,
            v_destination,
            'Picked Up'::order_status,
            round((0.5 + random() * 149.5)::NUMERIC, 2),
            v_service_type,
            v_estimated,
            v_created_at,
            v_created_at
        )
        RETURNING id INTO v_order_id;

        event_count := 3 + floor(random() * 6)::INT; -- 3..8 events
        v_event_time := v_created_at + ((1 + floor(random() * 10))::TEXT || ' hours')::INTERVAL;

        -- First event: always picked up
        v_event_type := 'Package Picked Up'::event_type;
        v_location := v_origin;
        v_notification_type := 'Status Update'::notification_type;
        v_message := format('Tracking %s: Package picked up at %s.', v_tracking, v_location);

        INSERT INTO shipment_events (order_id, event_type, location, description, occurred_at)
        VALUES (v_order_id, v_event_type, v_location, 'Package accepted by carrier', v_event_time);

        INSERT INTO notifications (order_id, business_id, type, message, is_read, created_at)
        VALUES (v_order_id, v_business_id, v_notification_type, v_message, random() < 0.35, v_event_time);

        -- Middle events
        IF event_count > 2 THEN
            FOR j IN 2..(event_count - 1) LOOP
                event_roll := random();
                v_event_type := CASE
                    WHEN event_roll < 0.18 THEN 'Arrived at FedEx Hub'::event_type
                    WHEN event_roll < 0.36 THEN 'Departed FedEx Hub'::event_type
                    WHEN event_roll < 0.63 THEN 'In Transit'::event_type
                    WHEN event_roll < 0.76 THEN 'Package at Local Facility'::event_type
                    WHEN event_roll < 0.87 THEN 'Out for Delivery'::event_type
                    WHEN event_roll < 0.93 THEN 'Delivery Attempted'::event_type
                    WHEN event_roll < 0.97 THEN 'Delay Reported'::event_type
                    ELSE 'Exception'::event_type
                END;

                v_event_time := v_event_time + ((2 + floor(random() * 18))::TEXT || ' hours')::INTERVAL;
                v_location := cities[1 + floor(random() * array_length(cities, 1))::INT];

                v_notification_type := CASE v_event_type
                    WHEN 'Delay Reported'::event_type THEN 'Delay Alert'::notification_type
                    WHEN 'Delivered'::event_type THEN 'Delivery Confirmed'::notification_type
                    WHEN 'Exception'::event_type THEN 'Exception Alert'::notification_type
                    WHEN 'Out for Delivery'::event_type THEN 'Out for Delivery'::notification_type
                    ELSE 'Status Update'::notification_type
                END;

                v_message := format('Tracking %s: %s in %s.', v_tracking, v_event_type::TEXT, v_location);

                INSERT INTO shipment_events (order_id, event_type, location, description, occurred_at)
                VALUES (v_order_id, v_event_type, v_location, 'Automated seeded event', v_event_time);

                INSERT INTO notifications (order_id, business_id, type, message, is_read, created_at)
                VALUES (v_order_id, v_business_id, v_notification_type, v_message, random() < 0.45, v_event_time);
            END LOOP;
        END IF;

        -- Final event influences final order status
        final_roll := random();
        v_event_type := CASE
            WHEN final_roll < 0.68 THEN 'Delivered'::event_type
            WHEN final_roll < 0.80 THEN 'Out for Delivery'::event_type
            WHEN final_roll < 0.90 THEN 'Delay Reported'::event_type
            WHEN final_roll < 0.96 THEN 'Exception'::event_type
            ELSE 'In Transit'::event_type
        END;

        v_event_time := v_event_time + ((2 + floor(random() * 12))::TEXT || ' hours')::INTERVAL;
        v_location := CASE
            WHEN v_event_type = 'Delivered'::event_type THEN v_destination
            ELSE cities[1 + floor(random() * array_length(cities, 1))::INT]
        END;

        v_notification_type := CASE v_event_type
            WHEN 'Delay Reported'::event_type THEN 'Delay Alert'::notification_type
            WHEN 'Delivered'::event_type THEN 'Delivery Confirmed'::notification_type
            WHEN 'Exception'::event_type THEN 'Exception Alert'::notification_type
            WHEN 'Out for Delivery'::event_type THEN 'Out for Delivery'::notification_type
            ELSE 'Status Update'::notification_type
        END;

        v_message := format('Tracking %s: %s at %s.', v_tracking, v_event_type::TEXT, v_location);

        INSERT INTO shipment_events (order_id, event_type, location, description, occurred_at)
        VALUES (v_order_id, v_event_type, v_location, 'Final seeded event', v_event_time);

        INSERT INTO notifications (order_id, business_id, type, message, is_read, created_at)
        VALUES (v_order_id, v_business_id, v_notification_type, v_message, random() < 0.55, v_event_time);

        v_status := CASE v_event_type
            WHEN 'Delivered'::event_type THEN 'Delivered'::order_status
            WHEN 'Out for Delivery'::event_type THEN 'Out for Delivery'::order_status
            WHEN 'Delay Reported'::event_type THEN 'Delayed'::order_status
            WHEN 'Exception'::event_type THEN 'Exception'::order_status
            ELSE 'In Transit'::order_status
        END;

        v_actual := CASE
            WHEN v_status = 'Delivered'::order_status THEN v_event_time::DATE
            ELSE NULL
        END;

        UPDATE orders
        SET
            status = v_status,
            actual_delivery = v_actual,
            updated_at = GREATEST(v_event_time, updated_at)
        WHERE id = v_order_id;

        IF i % 1000 = 0 THEN
            RAISE NOTICE 'Seed progress: % / % orders created', i, order_count;
        END IF;
    END LOOP;
END $$;

COMMIT;

-- Quick sanity checks:
-- SELECT count(*) FROM businesses;
-- SELECT count(*) FROM orders;
-- SELECT count(*) FROM shipment_events;
-- SELECT count(*) FROM notifications;
