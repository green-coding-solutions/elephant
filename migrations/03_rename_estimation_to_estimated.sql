DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'carbon' AND column_name = 'estimation'
  ) THEN
    ALTER TABLE carbon RENAME COLUMN estimation TO estimated;
  END IF;
END $$;
